import React from 'react';
import PropTypes from 'prop-types';
import { gettext } from '../../utils/constants';
import { Modal, ModalHeader, ModalBody, ModalFooter, Button } from 'reactstrap';

const propTypes = {
  currentResumableFile: PropTypes.object.isRequired,
  replaceRepetitionFile: PropTypes.func.isRequired,
  uploadFile: PropTypes.func.isRequired,
  cancelFileUpload: PropTypes.func.isRequired,
};

class UploadRemindDialog extends React.Component {

  toggle = () => {
    this.props.cancelFileUpload();
  }

  render() {

    let title = gettext('Replace file {filename}?');
    title = title.replace('{filename}', '<span class="a-simaulte">' + this.props.currentResumableFile.fileName + '</span>');
    return (
      <Modal isOpen={true} toggle={this.toggle}>
        <ModalHeader toggle={this.toggle} ><div dangerouslySetInnerHTML={{__html: title}}></div></ModalHeader>
        <ModalBody>
          <p>{gettext('A file with the same name already exists in this folder.')}</p>
          <p>{gettext('Replacing it will overwrite its content.')}</p>
        </ModalBody>
        <ModalFooter>
          <Button outline color="primary" onClick={this.props.replaceRepetitionFile}>{gettext('Replace')}</Button>
          <Button outline color="info" onClick={this.props.uploadFile}>{gettext("Don't Replace")}</Button>
          <Button outline color="danger" onClick={this.toggle}>{gettext('Cancel')}</Button>
        </ModalFooter>
      </Modal>
    );
  }
}

UploadRemindDialog.propTypes = propTypes;

export default UploadRemindDialog;
