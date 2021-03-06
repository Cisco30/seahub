# Copyright (c) 2012-2016 Seafile Ltd.
import os
import posixpath

from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from django.db import IntegrityError

from seaserv import seafile_api
from seahub.api2.authentication import TokenAuthentication
from seahub.api2.throttling import UserRateThrottle
from seahub.api2.utils import api_error
from seahub.constants import PERMISSION_READ_WRITE
from seahub.views import check_folder_permission

from seahub.drafts.models import Draft, DraftReview, DraftReviewExist, \
        DraftFileConflict, ReviewReviewer
from seahub.drafts.signals import update_review_successful


class DraftReviewsView(APIView):
    authentication_classes = (TokenAuthentication, SessionAuthentication)
    permission_classes = (IsAuthenticated, )
    throttle_classes = (UserRateThrottle, )

    def get(self, request, format=None):
        """ List all reviews related to the user and their corresponding reviewers based on the review status
        case1: List the reviews created by the user and their associated reviewers by status
        case2: List the reviews of the user as reviewer and their associated reviewers by status
        status: open / finished / closed
        """
        username = request.user.username

        st = request.GET.get('status', 'open')

        if st not in ('open', 'finished', 'closed'):
            error_msg = 'Status invalid.'
            return api_error(status.HTTP_400_BAD_REQUEST, error_msg)

        # case1: List the reviews created by the user and their associated reviewers by status
        reviews_1 = DraftReview.objects.get_reviews_by_creator_and_status(creator=username, status=st)

        # case2: List the reviews of the user as reviewer and their associated reviewers by status
        reviews_2 = DraftReview.objects.get_reviews_by_reviewer_and_status(reviewer=username, status=st)

        data = reviews_1 + reviews_2

        return Response({'data': data})

    def post(self, request, format=None):
        """Create a draft review if the user has read permission to the repo
        """
        draft_id = request.data.get('draft_id', '')
        try:
            d = Draft.objects.get(pk=draft_id)
        except Draft.DoesNotExist:
            return api_error(status.HTTP_404_NOT_FOUND,
                             'Draft %s not found.' % draft_id)

        # perm check
        perm = check_folder_permission(request, d.origin_repo_id, '/')

        if perm is None:
            return api_error(status.HTTP_403_FORBIDDEN,
                             'Permission denied.')

        username = request.user.username
        try:
            d_r = DraftReview.objects.add(creator=username, draft=d)
        except (DraftReviewExist):
            return api_error(status.HTTP_409_CONFLICT, 'Draft review already exists.')

        return Response(d_r.to_dict())


class DraftReviewView(APIView):
    authentication_classes = (TokenAuthentication, SessionAuthentication)
    permission_classes = (IsAuthenticated, )
    throttle_classes = (UserRateThrottle, )

    def put(self, request, pk, format=None):
        """update review status 
        Close: the user has read permission to the repo
        Publish: the user has read-write permission to the repo
        """

        st = request.data.get('status', '')
        if not st:
            return api_error(status.HTTP_400_BAD_REQUEST,
                             'Status %s invalid.')

        try:
            r = DraftReview.objects.get(pk=pk)
        except DraftReview.DoesNotExist:
            return api_error(status.HTTP_404_NOT_FOUND,
                             'Review %s not found' % pk)

        uuid = r.origin_file_uuid
        origin_file_path = posixpath.join(uuid.parent_path, uuid.filename)

        perm = check_folder_permission(request, r.origin_repo_id, '/')

        # Close: the user has read permission to the repo
        if st == 'closed':
            if perm is None:
                error_msg = 'Permission denied.'
                return api_error(status.HTTP_403_FORBIDDEN, error_msg)

            r.status = st
            r.save()

        # Publish: the user has read-write permission to the repo
        if st == 'finished':
            if perm != PERMISSION_READ_WRITE:
                error_msg = 'Permission denied.'
                return api_error(status.HTTP_403_FORBIDDEN, error_msg)

            try:
                d = Draft.objects.get(pk=r.draft_id_id)
            except Draft.DoesNotExist:
                return api_error(status.HTTP_404_NOT_FOUND,
                                 'Draft %s not found.' % pk)

            try:
                d.publish()
            except (DraftFileConflict, IntegrityError):
                return api_error(status.HTTP_409_CONFLICT,
                             'There is a conflict between the draft and the original file')

            # if it is a new draft
            # case1. '/path/test(draft).md' ---> '/path/test.md'
            # case2. '/path/test(dra.md' ---> '/path/test(dra.md'
            if d.draft_file_path == origin_file_path:
                new_draft_dir = os.path.dirname(origin_file_path)
                new_draft_name = os.path.basename(origin_file_path)

                draft_flag = os.path.splitext(new_draft_name)[0][-7:]

                # remove `(draft)` from file name
                if draft_flag == '(draft)':
                    f = os.path.splitext(new_draft_name)[0][:-7]
                    file_type = os.path.splitext(new_draft_name)[-1]
                    new_draft_name = f + file_type

                if new_draft_dir == '/':
                    origin_file_path = new_draft_dir + new_draft_name
                else:
                    origin_file_path = new_draft_dir + '/' + new_draft_name

                r.draft_file_path = origin_file_path

            # get draft published version
            file_id = seafile_api.get_file_id_by_path(r.origin_repo_id, origin_file_path)
            r.publish_file_version = file_id
            r.status = st
            r.save()
            d.delete()

        reviewers = ReviewReviewer.objects.filter(review_id=r)
        # send notice to other reviewers if has
        if reviewers:
            for i in reviewers:
                #  If it is a reviewer operation, exclude it.
                if i.reviewer == request.user.username:
                    continue

                update_review_successful.send(sender=None, from_user=request.user.username,
                                              to_user=i.reviewer, review_id=r.id, status=st)

        # send notice to review owner
        if request.user.username != r.creator:
            update_review_successful.send(sender=None, from_user=request.user.username,
                                          to_user=r.creator, review_id=r.id, status=st)

        result = r.to_dict()

        return Response(result)
