import csv
import datetime
import json
import os
from pytz import timezone
import re
from shutil import move
from io import StringIO
import logging
import xml.etree.cElementTree as ET
from odoo.exceptions import ValidationError
from odoo import api, _, fields, SUPERUSER_ID, tools, models
from .exceptions import EdiIgnorePartnerError, EdiValidationError

_logger = logging.getLogger(__name__)

##############################################################################
#
#    The EDIFlow class defines the model layout for an EDI Flow. A Flow
#    has a name and a direction. A Flow cannot be directly maintained using
#    a screen in OpenERP. You define a new flow in another module together
#    with how it should be processed. Look for config.xml files in other modules.
#
##############################################################################
class edi_tools_edi_flow(models.Model):
    _name = "edi.tools.edi.flow"

    name = fields.Char('Flow Name', size=64, required=True, readonly=True)
    direction = fields.Selection([('in', 'Incoming'), ('out', 'Outgoing')], 'Direction', required=True, readonly=True)
    model = fields.Char('Model Name', size=64, required=True, readonly=True)
    method = fields.Char('Method Name', size=64, required=False, readonly=True)
    validator =  fields.Char('Validator Name', size=64, required=False, readonly=True)
    partner_resolver = fields.Char('Partner Resolver Name', size=64, required=False, readonly=True)
    process_after_create = fields.Boolean('Automatically process after create')
    allow_duplicates =  fields.Boolean('Allow duplicate references')
    ignore_partner_ids = fields.Many2many('res.partner', 'edi_tools_ignore_partner_rel', 'flow_id', 'partner_id', help="A list of partners that need to be ignored. The content is retrieved from the edi document.")


##############################################################################
#
#    The PartnerFlow class defines the relation to a partner and an EDIFlow.
#    You can temporarily disable a flow so it becomes unavailable.
#
##############################################################################
class edi_tools_edi_partnerflow(models.Model):
    _name = "edi.tools.edi.partnerflow"

    partnerflow_id = fields.Many2one('res.partner', 'Partner Flow Name', ondelete='cascade', required=True, select=True, readonly=False)
    flow_id = fields.Many2one('edi.tools.edi.flow', 'Flow', required=True, select=True, readonly=False)
    partnerflow_active = fields.Boolean('Active')


##############################################################################
#
#    The document class is the heart of the framework. A document is an
#    abstraction of a file in a given flow for a given partner. It can be
#    processed in many ways and has a given state/state history.
#
##############################################################################
class edi_tools_edi_document(models.Model):
    _name = "edi.tools.edi.document"
    _inherit = ['mail.thread']
    _description = "EDI Document"

    _error_file_already_exists_at_destination = 'file_already_exists_at_destination'
    _error_file_move_failed                   = 'file_move_failed'


    
    def _function_message_get(self):
        ''' edi.tools.edi.document:_function_message_get()
        -----------------------------------------------------
        This method helps to dynamically calculate the
        message field to always show the latest OpenChatter message body.
        ----------------------------------------------------------------- '''
        for document in self:
            if document.message_ids:
                document.message = re.sub('<[^<]+?>', '',document.message_ids[0].body)


    name = fields.Char('Name', size=256, required=True, readonly=True)
    location = fields.Char('File location', size=256, required=True, readonly=False)
    partner_id = fields.Many2one('res.partner', 'Partner', readonly=True, required=True)
    flow_id = fields.Many2one('edi.tools.edi.flow', 'EDI Flow', readonly=True, required=True)
    message = fields.Char(compute=_function_message_get, string='Message', store=True)
    reference = fields.Char('Reference', size=64, required=False, readonly=True)
    state = fields.Selection([('new', 'New'),
                                   ('ready', 'Ready'),
                                   ('processing', 'Processing'),
                                   ('in_error', 'In Error'),
                                   ('processed', 'Processed'),
                                   ('archived', 'Archived')], 'State', required=True, readonly=True)
    content = fields.Text('Content',readonly=True, states={'new': [('readonly', False)], 'in_error': [('readonly', False)]})
    create_date = fields.Datetime('Creation date')


    #def unlink(self, cr, uid, ids, context=None):
    #    ''' edi.tools.edi.document:unlink()
    #    --------------------------------------
    #    This method overwrites the default unlink/delete() method
    #    to make sure a document can only be deleted when it's
    #    in state "in_error"
    #    --------------------------------------------------------- '''
    #    assert len(ids) == 1
    #    document = self.browse(cr, uid, ids, context=context)[0]
    #    if document.state != 'in_error':
    #        raise osv.except_osv(_('Document deletion failed!'), _('You may only delete a document when it is in state error.'))
    #    return super(edi_tools_edi_document, self).unlink(cr, uid, ids, context=context)

    @api.model
    def check_location(self, doc_id):
        ''' This method checks wether or not the documents corresponding
        file is still where it's supposed to be. '''
        document = self.browse(doc_id)
        return os.path.isfile(os.path.join(document.location, document.name))

    @api.model
    def move(self, doc_id, to_folder):
        ''' This method moves a file/document from a
        given state to another. '''

        # Before we try to move the file, check if
        # its still there and everything is ok
        if not self.check_location(doc_id):
            _logger.debug("File for edi document %d is not at the location we expect it to be. Aborting", doc_id)
            return False

        # The moving of files should be allowed so let's carry on!
        document = self.browse(doc_id)
        from_path = os.path.join(document.location, document.name)
        to_path   = False

        # Specialized path determination for state:new, given
        # that the file isn't part of the directory structure yet
        if document.state == 'new':
            to_path = os.path.join(document.location, to_folder, document.name)

        # Path determination for archiving
        else:
            path, dummy = os.path.split(document.location)
            to_path = os.path.join(path, to_folder, document.name)

        _logger.debug("Moving document with id %d (%s)from folder %s to folder %s", document.id, document.name, from_path, to_path)

        # Make sure the file doesn't exist already
        # at the to_path location
        # ----------------------------------------
        #if os.path.isfile(to_path):
        #    self.message_post(cr, uid, document.id, body='Could not move file, it already exists at the destination folder.')
        #    return {'error' : self._error_file_already_exists_at_destination}

        # Actually try to move the file using shutil.move()
        # This step also includes serious error handling to validate
        # the file was actually moved so we can catch a corrupted document
        # ----------------------------------------------------------------
        try:
            move(from_path, to_path)
            _logger.debug("Move file successful")
        except Exception:
            document.message_post(body='An unknown error occurred during the moving of the file.')
            return {'error' : self._error_file_move_failed}

        # Check if the move actually took place
        if os.path.isfile(os.path.join(document.location, document.name)):
            document.message_post(body='File moving failed, it is still present at the starting location.')
            return {'error' : self._error_file_move_failed}
        elif os.path.isfile(to_path) == False:
            document.message_post(body='File moving failed, it is not present at the target location.')
            return {'error' : self._error_file_move_failed}

        path, dummy = os.path.split(to_path)
        document.write({'location' : path})
        return True

    @api.model
    def position_document(self, partner_id, flow_id, content, content_type='json'):
        ''' This method will position the given content as an EDI
        document ready to be picked up for a given partner/flow
        combination. It will make sure the partner is actually
        listening to this flow. '''

        # Make the partner listen
        partner_db = self.env['res.partner']
        partner_db.listen_to_edi_flow(partner_id, flow_id)

        # Create a file from the given content
        now = datetime.datetime.now()
        name = now.strftime("%d_%m_%Y_%H_%M_%S") + ".csv"
        ICPSudo = self.env['ir.config_parameter'].sudo()
        edi_directory = ICPSudo.get_param('edi.edi_root_directory', default='/EDI')

        path = os.path.join(os.sep, edi_directory, self.env.cr.dbname, str(partner_id), str(flow_id), name)
        with open(path, 'wb') as temp_file:
            if content_type == 'csv':
                writer = csv.writer(temp_file, delimiter=',', quotechar='"')
                for line in content:
                    writer.writerow(line)

            elif content_type == 'json':
                for line in content:
                    temp_file.write(line)

        return True

    
    def copy(self, default=None):
        for document in self:
            if default is None:
                default = {}
            name = self.create_unique_name_from_existing_name(document.name)
            # write document to disk
            ICPSudo = self.env['ir.config_parameter'].sudo()
            edi_directory = ICPSudo.get_param('edi.edi_root_directory', default='/EDI')
            location = os.path.join(os.sep, edi_directory, self.env.cr.dbname, str(document.partner_id.id), str(document.flow_id.id), 'imported')
            with open (os.path.join(location, name), "w") as f:
                f.write(document.content)

            default.update({
              'name': name,
              'location': location,
              'state': 'new',
              'reference': None,
              'processed': False
            })
            res = super(edi_tools_edi_document, self).copy(default)
            return res

    @api.model
    def create_unique_name_from_existing_name(self, existing_name):
        # remove the file extension
        name_without_extension, extension = os.path.splitext(existing_name)
        # check if the file was duplicated before
        res = re.findall(r'-([0-9]*)$', name_without_extension)
        if res:
          counter = int(res[0]) + 1
          name_without_extension = re.sub(r'-[0-9]*$', "-%d"%(counter), name_without_extension)
        else:
          name_without_extension = name_without_extension + '-1'
        # append extension
        name = name_without_extension + extension
        # make sure the name doesn't already exist
        ids = self.search([('name','=',name)])
        if not ids:
          return name
        else:
          return self.create_unique_name_from_existing_name(name)

##############################################################################
#
#    The incoming document class represents an incoming file and is subject
#    to the most complicated workflow in the EDI system.
#
##############################################################################
class edi_tools_edi_document_incoming(models.Model):
    _name = "edi.tools.edi.document.incoming"
    _inherit = ['edi.tools.edi.document']
    _description = "Incoming EDI Document"
    _order = "create_date desc"

    processed = fields.Boolean('Processed', readonly=True)

    
    def copy(self, default=None):
        default = default and default.copy() or {}
        return super(edi_tools_edi_document_incoming, self).copy(default=default)

    
    def document_manual_process(self):
        for record in self:
            record.action_processing()
            return True

    @api.model
    def create_from_file(self, location, name):
        ''' This method is a wrapper method for the standard
        OpenERP create() method. It will prepare the vals[] for
        the standard method based on the file's location, flow & partner. '''

        _logger.debug("Creating edi document from file %s at location %s", name, location)

        if os.path.isfile(os.path.join(location, name)) == False:
            raise ValidationError(_('File not found: {!s}'.format(os.path.join(location, name))))

        vals = {}
        vals['name'] = name
        vals['location'] = location

        folders = []
        path = location
        while 1:
            path, folder = os.path.split(path)
            if folder != "":
                folders.append(folder)
            else:
                if path != "":
                    folders.append(path)
                break
        folders.reverse()

        vals['partner_id'] = folders[len(folders) - 2]
        vals['flow_id'] = folders[len(folders) - 1]
        vals['state'] = 'new'

        # Read the file contents
        with open (os.path.join(location, name), "r") as f:
            vals['content'] = f.read()

        # Create the actual EDI document, triggering
        # the workflow to start
        new_id = self.create(vals)
        _logger.debug("Created edi document with id %d", new_id)
        if new_id != False:
            self.move(new_id.id, 'imported')
        return new_id

    def create_from_web_request(self, partner, flow, reference, content, data_type):
        ''' This method creates a new incoming EDI document based on the
        provided input. It provides an easy way to create EDI documents using
        the web. '''

        _logger.debug("Creating edi document from web request for partner %s, flow %s, reference %s", partner, flow, reference)

        # Find the correct EDI flow
        model_db = self.env['ir.model.data']
        flow_id = model_db.search([('name', '=', flow), ('model','=','edi.tools.edi.flow')])
        if not flow_id or not flow: return 'Parameter "flow" could not be resolved, request aborted.'
        flow_id = model_db.browse(flow_id)[0]
        flow_id = flow_id.res_id
        flow_object = self.env['edi.tools.edi.flow'].browse(flow_id)
        _logger.debug("Flow found %d (%s)", flow_id, flow_object.name)

        # Find the correct partner
        partner_id = model_db.search([('name', '=', partner), ('model','=','res.partner')])
        if not partner_id or not partner: return 'Parameter "partner" could not be resolved, request aborted.'
        partner_id = model_db.browse(partner_id)[0]
        partner_id = partner_id.res_id
        _logger.debug("Partner found %d for name provided (%s)", partner_id, partner)

        if not reference: return 'Parameter "reference" cannot be empty, request aborted.'
        if not content:   return 'Parameter "content" cannot be empty, request aborted.'
        if data_type != 'xml' and data_type != 'json':
            return 'Parameter "data_type" should be either "xml" or "json", request aborted.'

        # Make sure the partner is listening to this flow
        partnerflow_id = self.env['edi.tools.edi.partnerflow'].search([('partnerflow_id','=', partner_id), ('flow_id','=', flow_id), ('partnerflow_active','=', True)])
        if not partnerflow_id: return 'The provided partner is not currently listening to the provided EDI flow, request aborted.'

        # Make sure the file doesn't already exist, unless duplicates are allowed
        filename = '.'.os.path.join([reference, data_type])
        if not flow_object.allow_duplicates:
            doc_id = self.search([('flow_id', '=', flow_id), ('partner_id', '=', partner_id), ('reference', '=', reference)])
            if doc_id: return 'This reference has already been processed, request aborted.'
        ICPSudo = self.env['ir.config_parameter'].sudo()
        edi_directory = ICPSudo.get_param('edi.edi_root_directory', default='/EDI')
        location = os.path.join(os.sep, edi_directory, self.env.cr.dbname, str(partner_id), str(flow_id), 'imported')

        values = {
            'name'       : filename,
            'reference'  : reference,
            'partner_id' : partner_id,
            'flow_id'    : flow_id,
            'content'    : content,
            'state'      : 'new',
            'location'   : location,
        }

        # If the document creation is successful, write the file to disk
        doc_id = self.create(values)
        if not doc_id: return 'Something went wrong trying to create the EDI document, request aborted.'
        try:
            with open (os.path.join(location, filename), "w") as f:
                f.write(content.encode('utf8'))
        except Exception as e:
            doc_id.write({'state':'in_error'})
            doc_id.unlink()
            return 'Something went wrong writing the file to disk, request aborted. Error given: {!s}'.format(str(e))

        # Push forward the document if customized
        if flow_object.process_after_create:
            doc_id.action_ready()

        return True

    @api.model
    def import_process(self):
        ''' This method reads the file system for all EDI active partners and
        their corresponding flows and will import the files to create active
        EDI documents. Once a file has been imported as a document, it needs
        to go through the entire EDI workflow process. '''
        _logger.debug('Start the EDI document import process.')
        # Find all active EDI partners
        partner_db = self.env['res.partner']
        pids = partner_db.search([('edi_relevant', '=', True)])
        if not pids:
            _logger.debug('No active EDI partners at the moment, processing is done.')
            return True

        # Loop over each individual partner and scrobble through their active flows
        partners = pids
        for partner in partners:
            _logger.debug("Processing edi relevant partner %d (%s)", partner.id, partner.name)
            ICPSudo = self.env['ir.config_parameter'].sudo()
            edi_directory = ICPSudo.get_param('edi.edi_root_directory', default='/EDI')
            root_path = os.path.join(os.sep, edi_directory, self.env.cr.dbname, str(partner.id))
            if not os.path.exists(root_path):
                _logger.error("Folder does not exist for partner %d (%s), creating.", partner.id, partner.name)
                partner.maintain_edi_directories()

            if not partner.edi_flows:
                _logger.debug("No edi flows defined for partner %d", partner.id)

            for flow in partner.edi_flows:
                if flow.partnerflow_active == False or flow.flow_id.direction != 'in': continue
                _logger.debug("Processing active incoming flow %d (%s)", flow.id, flow.flow_id.name)

                # We've found an active flow, let's check for new files
                # A file is determined as new if it isn't assigned to a
                # workflow folder yet.
                sub_path = os.path.join(root_path, str(flow.flow_id.id))
                if not os.path.exists(sub_path):
                    raise ValidationError(_('EDI folder missing for partner {!s}, flow {!s}'.format(flow.flow_id.name)))

                files = [ f for f in os.listdir(sub_path) if os.path.isfile(os.path.join(sub_path, f)) ]
                if not files:
                    _logger.debug("No files found in directory %s", sub_path)
                    continue

                # If we get all the way over here, it means we've
                # actually found some new files :)
                for f in files:
                    _logger.debug("File found in directory %s: %s", sub_path, f)
                    # Entering ultra defensive mode: make sure that this
                    # file isn't already converted to an EDI document yet!
                    # Unless this is specifically allowed by the flow
                    if not flow.flow_id.allow_duplicates:
                        duplicate = self.search([('partner_id', '=', partner.id),
                                                          ('flow_id', '=', flow.flow_id.id),
                                                          ('name', '=', f)])
                        if len(duplicate.ids) > 0:
                            _logger.debug("Duplicate file. Skipping")
                            continue

                    # Actually create a new EDI Document
                    # This also triggers the workflow creation
                    new_doc = self.create_from_file(sub_path, f)
                    if flow.flow_id.process_after_create:
                        _logger.debug("Trigger workflow ready for edi document %d", new_doc.id)
                        new_doc.action_ready()

        _logger.debug('End the document import process.')
        return True

    @api.model
    def document_process(self):
        ''' This method is the main scheduler which will process all the
        incoming EDI documents which are currently waiting in status 'ready'.
        The process will move all the documents to the state "processing". '''

        # Find all documents that are ready to be processed
        _logger.warning('Start the EDI document processor.')
        documents = self.search([('state', '=', 'ready')])
        if not documents:
            _logger.warning('No documents found, processing is done.')
            return True

        # Mark all of these documents as in 'processing' to make sure they don't
        # get picked up twice. The actual processing will be done for us by the
        # workflow method action_processed().
        for document in documents:
            _logger.debug("Trigger workflow processing for edi document %d", document)
            document.action_processed()

        _logger.debug('End the EDI document processor.')
        return True

    
    def valid(self):
        ''' edi.tools.edi.document.incoming:valid()
        ----------------------------------------------
        This method checks wether or not the current document
        is valid according to the relevant EDI Flow implementation.
        If there is no implementation, it is valid by default.
        ----------------------------------------------------------- '''
        for document in self:
            # Perform a basic validation, depending on the filetype
            # -----------------------------------------------------
            filetype = document.name.split('.')[-1]
            if filetype == 'csv':
                try:
                    dummy_file = StringIO(document.content)
                    reader = csv.reader(dummy_file, delimiter=',', quotechar='"')
                except Exception:
                    document.message_post(body='Error found: content is not valid CSV.')
                    return False

            elif filetype == 'json':
                try:
                    data = json.loads(document.content)
                    if not data:
                        document.message_post(body='Error found: content is not valid JSON.')
                        return False
                except Exception:
                    document.message_post(body='Error found: content is not valid JSON.')
                    return False

            # Perform custom validation
            # -------------------------
            if not document.flow_id.validator:
                return True

            validator = getattr(self.env[document.flow_id.model], document.flow_id.validator)
            _logger.debug("Perform custom validator '%s.%s' for flow %d (%s)", document.flow_id.model, document.flow_id.validator, document.flow_id.id, document.flow_id.name)
            try:
                return validator(document.id)
            except EdiValidationError as e:
                document.message_post(body=tools.ustr(e))
                return False
            except Exception as e:
                document.message_post(body='Programming error occured during validation:{!s}'.format(str(e)))
                return False

    
    def action_new(self):
        ''' edi.tools.edi.document.incoming:action_new()
        ---------------------------------------------------
        This method is called when the object is created by the
        workflow engine. The object already exists at this point
        and we'll use this method to move the file into the EDI
        document system. This method will also trigger the
        automated validation workflow steps.
        -------------------------------------------------------- '''
        self.write({ 'state' : 'new' })
        return True

    
    def action_in_error(self):
        ''' edi.tools.edi.document.incoming:action_in_error()
        --------------------------------------------------------
        This method can be called from a number of places. For example
        when a user tries to mark a document as ready, or if processing
        resulted in an error. Putting a document in error will also
        put the "processed" attribute back to false.
        --------------------------------------------------------------- '''
        self.write({ 'state' : 'in_error', 'processed' : False })
        return True

    
    def action_ready(self):
        ''' edi.tools.edi.document.incoming:action_ready()
        -----------------------------------------------------
        This method is called when the user marks the document as
        ready. This means the document is ready to be picked up
        by the EDI Processing scheduler. Before the document is put
        to ready, it first passed through the validator() method
        *if* there's one defined in the concrete EDI Flow implementation
        ---------------------------------------------------------------- '''
        self.message_post(body='EDI Document marked as ready for processing.')
        self.write({ 'state' : 'ready' })
        return True

    
    def action_processing(self):
        ''' edi.tools.edi.document.incoming:action_processing()
        ----------------------------------------------------------
        This method is called by the document_processor to mark
        documents as in processing. This is to make sure that documents
        don't get picked up by the system twice.
        --------------------------------------------------------------- '''
        self.write({ 'state' : 'processing' })
        return True

    
    def action_processed(self):
        ''' edi.tools.edi.document.incoming:action_processed()
        ---------------------------------------------------------
        This method is called by the document_processor to mark
        documents as having been processed. A user can't call this
        method manually.
        ---------------------------------------------------------- '''
        for document in self:
            if not document.valid(): 
                self.write({ 'state' : 'in_error' })
                return False
            processor = getattr(self.env[document.flow_id.model], document.flow_id.method)
            result = False
            try:
                result = processor(document.id)
            except EdiIgnorePartnerError as e:
                document.message_post(body='Ignoring the document. {!s}'.format(str(e)))
                self.write({ 'state' : 'processed', 'processed' : True })
            except Exception as e:
                document.message_post(body='Error occurred during processing, error given: {!s}'.format(str(e)))
                self.state = 'in_error'
                self.write({ 'state' : 'in_error' })
                return True
                continue
            if result:
                document.message_post(body='EDI Document successfully processed.')
                self.write({ 'state' : 'processed', 'processed' : True })
            else:
                document.message_post(body='Error occurred during processing, the action was not completed.')
                self.write({ 'state' : 'in_error' })
            _logger.debug("Document %s Processed with state %s", str(document.id), str(document.state))
            return True

    
    def action_archive(self):
        ''' edi.tools.edi.document.incoming:action_archive()
        -------------------------------------------------------
        This method is called when the user marks the document
        as ready for archiving. This is the final step in the
        workflow and marks it is being done.
        ------------------------------------------------------ '''
        for record in self:
            record.write({ 'state' : 'archived' })
            self.move(record.id, 'archived')
            record.message_post(body='EDI Document successfully archived.')
            return True

##############################################################################
#
#    The outgoing document class represents an outgoing file.
#
##############################################################################
class edi_tools_edi_document_outgoing(models.Model):
    _name = "edi.tools.edi.document.outgoing"
    _inherit = ['edi.tools.edi.document']
    _description = "Outgoing EDI Document"
    _order = "create_date desc"

    _flow_not_found        = 'flow_not_found'
    _content_invalid       = 'content_invalid'
    _no_listening_partners = 'no_listening_partners'
    _file_creation_error   = 'file_creation_error'

    @api.model
    def create_from_content(self, reference, content, partner_id, model, method, type='JSON'):
        ''' edi.tools.edi.document.outgoing:create_from_content()
        ------------------------------------------------------------
        This method accepts content and creates an EDI document
        for each currently actively listening partner.
        ------------------------------------------------------- '''

        # Resolve the method to an EDI flow
        # ---------------------------------
        flow_db = self.env['edi.tools.edi.flow']
        flow = flow_db.search([('model', '=', model),('method', '=', method)])[0]
        if not flow:
            return self._flow_not_found
        # Make sure the provided content is valid
        # ---------------------------------------
        if type == 'JSON':
            try:
                data = json.loads(json.dumps(content))
                if not data: return self._content_invalid
            except Exception:
                return self._content_invalid

        # Start preparing the document
        # ----------------------------
        vals = {}

        # get user's timezone
        user_db = self.env['res.users']
        user = user_db.browse(SUPERUSER_ID)
        if user.partner_id.tz:
            tz = timezone(user.partner_id.tz) or timezone('UTC')
        else:
            tz = timezone('UTC')
        now = datetime.datetime.now(tz)
        vals['flow_id'] = flow.id

        if type == 'STRING':
            vals['name'] = reference.replace("/", "_") + '_' + now.strftime("%d_%m_%Y_%H_%M_%S") + ".json"
            vals['content'] = content
        elif type == 'XML':
            vals['name'] = reference.replace("/", "_") + '_' + now.strftime("%d_%m_%Y_%H_%M_%S") + ".xml"
            vals['content'] = ET.tostring(content, encoding='UTF-8', method='xml')
        else:
            vals['name'] = reference.replace("/", "_") + '_' + now.strftime("%d_%m_%Y_%H_%M_%S") + ".json"
            vals['content'] = json.dumps(content)

        vals['reference'] = reference
        vals['partner_id'] = partner_id
        ICPSudo = self.env['ir.config_parameter'].sudo()
        edi_directory = ICPSudo.get_param('edi.edi_root_directory', default='/EDI')
        vals['location']   = os.path.join(os.sep, edi_directory, self.env.cr.dbname, str(partner_id), str(flow.id))
        vals['state'] = 'new'

        # Create the EDI document
        super(edi_tools_edi_document, self).create(vals)

        # Physically create the file
        try:
            f = open(os.path.join(vals['location'], vals['name']), "w")
            f.write(vals['content'])
            f.close()
        except Exception as e:
            return str(e)

        return True

    
    def document_manual_process(self):
        '''Button action to manually process outgoing document'''
        for document in self:
            processor = getattr(self.env[document.flow_id.model], document.flow_id.method)
            result = False
            try:
                result = processor(document.id)
            except Exception as e:
                document.message_post(body='Error occurred during processing, error given: {!s}'.format(str(e)))
                document.write({ 'state' : 'in_error' })
            # the implementation can write messages in the document giving more info
            if result:
                document.message_post(body='EDI Document successfully processed.')
                document.write({ 'state' : 'processed', 'processed' : True })
            else:
                document.message_post(body='Error occurred during processing, the action was not completed.')
                document.write({ 'state' : 'in_error' })
            return result
