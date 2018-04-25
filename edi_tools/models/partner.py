from odoo import models, fields, api
from odoo.exceptions import ValidationError
import logging
import os

_logger = logging.getLogger(__name__)

class edi_partner(models.Model):
    _inherit = "res.partner"

    edi_relevant = fields.Boolean('EDI Relevant')
    edi_flows = fields.One2many('edi.tools.edi.partnerflow', 'partnerflow_id', 'EDI Flows', readonly=False)

    @api.model
    def create(self, vals):
        ''' Make sure all required EDI directories are created '''
        new_id = super(edi_partner, self).create(vals)
        new_id.maintain_edi_directories()
        self.update_partner_overview_file()
        return new_id

    @api.multi
    def write(self, vals):
        ''' Make sure all required EDI directories are created '''
        result = super(edi_partner, self).write(vals)
        self.maintain_edi_directories()
        self.update_partner_overview_file()
        return result

    @api.multi
    def maintain_edi_directories(self):
        for partner in self:
            ''' This method creates all EDI directories for a given set of partners.
            A root folder based on the partner_id is created, with a set of sub
            folders for all the EDI flows he is subscried to. '''

            _logger.debug('Maintaining the EDI directories')
            _logger.debug('The present working directory is: {!s}'.format(os.getcwd()))

            # Only process partners that are EDI relevant
            if not partner.edi_relevant:
                continue
            _logger.debug("Processing partner %d (%s)", partner.id, partner.name)

            # Find and/or create the root directory for this partner
            #raise ValidationError(str(self.env['edi.tools.config.settings'].default_get(['edi_root_directory'])))
            ICPSudo = self.env['ir.config_parameter'].sudo()
            edi_directory = ICPSudo.get_param('edi.edi_root_directory', default='/EDI')
            root_path = os.path.join(os.sep, edi_directory, self.env.cr.dbname, str(partner.id))
            if not os.path.exists(root_path):
                _logger.debug('Required directory missing, attempting to create: {!s}'.format(root_path))
                os.makedirs(root_path)

            # Loop over all the EDI Flows this partner is subscribed to
            # and make sure all the necessary sub folders exist.
            for flow in partner.edi_flows:
                sub_path = os.path.join(root_path, str(flow.flow_id.id))
                if not os.path.exists(sub_path):
                    _logger.debug('Required directory missing, attempting to create: {!s}'.format(sub_path))
                    os.makedirs(sub_path)

                # Create folders to help the system keep track
                if flow.flow_id.direction == 'in':
                    _logger.debug("Creating directories imported and archived for incoming edi documents")
                    if not os.path.exists(os.path.join(sub_path, 'imported')): os.makedirs(os.path.join(sub_path, 'imported'))
                    if not os.path.exists(os.path.join(sub_path, 'archived')): os.makedirs(os.path.join(sub_path, 'archived'))

    @api.model
    def update_partner_overview_file(self):
        ''' This method creates a file for eachin the root EDI directory to give a matching
        list of partner_id's with their current corresponding names for easier
        lookups. '''

        _logger.debug('Updating the EDI partner overview file')
        _logger.debug('The present working directory is: {!s}'.format(os.getcwd()))

        # Find all active EDI partners
        partner_db = self.env['res.partner']
        pids = partner_db.search([('edi_relevant', '=', True)])
        if not pids:
            return True

        # Loop over each partner and create a simple.debug list
        content = ""
        for partner in pids:
            content += str(partner.id) + " " + partner.name + "\n"

            for flow in partner.edi_flows:
                content += "\t" + str(flow.flow_id.id) + " " + flow.flow_id.name + "\n"

        # Write this.debug to a helper file
        #edi_directory = self.env['edi.tools.config.settings'].default_get(['default_edi_root_directory'])['default_edi_root_directory']
        #edi_directory = self.env['edi.tools.config.settings'].search([], limit=1).default_edi_root_directory
        ICPSudo = self.env['ir.config_parameter'].sudo()
        edi_directory = ICPSudo.get_param('edi.edi_root_directory', default='/EDI')
        if not os.path.exists(os.path.join(edi_directory, self.env.cr.dbname)):
            os.makedirs(os.path.join(edi_directory, self.env.cr.dbname))
        file_path = os.path.join(edi_directory, self.env.cr.dbname, "partners.edi")
        _logger.debug('Attempting to look up the partner file at: {!s}'.format(file_path))
        f = open(file_path ,"w")
        f.write(content)
        f.close()

    @api.model
    def listen_to_edi_flow(self, partner_id, flow_id):
        ''' This method adds an EDI flow to a partner '''
        if not partner_id or not flow_id: return False
        partner = self.browse(partner_id)
        exists = [flow for flow in partner.edi_flows if flow.flow_id.id == flow_id]
        if exists:
            vals = {'edi_flows': [[1, exists[0].id, {'partnerflow_active': True, 'flow_id': flow_id}]]}
            return partner.write(vals)
        else:
            vals = {'edi_flows': [[0, False, {'partnerflow_active': True, 'flow_id': flow_id}]]}
            return partner.write(vals)

    @api.model
    def is_listening_to_flow(self, partner_id, flow_id):
        ''' This method checks wether or not a partner
        is listening to a given flow. '''
        if not partner_id or not flow_id: return False

        partner = self.browse(partner_id)
        if not partner.edi_relevant: return False
        exists = next(flow for flow in partner.edi_flows if flow.flow_id.id == flow_id)
        if exists and exists.partnerflow_active:
            return True
        return False