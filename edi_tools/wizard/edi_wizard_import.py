# -*- coding: utf-8 -*-
##############################################################################
# For copyright and license notices, see __openerp__.py file in root directory
##############################################################################
import base64
import logging
import os
from odoo import fields, models, api
LOGGER = logging.getLogger(__name__)

class EdiWizardImport(models.TransientModel):
    _name = 'edi.tools.import'
    _description = 'Manually import EDI File'

    partner_id = fields.Many2one('res.partner', 'Partner', required=True)
    flow_id = fields.Many2one('edi.tools.edi.flow', 'EDI Flow', required=True)
    edi_files = fields.Many2many(string='EDI FileS', comodel_name="ir.attachment", relation="m2m_ir_attachment_relation", column1="m2m_id", column2="attachment_id", required=True)

    def import_edi(self):
        LOGGER.warning('IMPORT EDI FILES %s', self.edi_files)
        LOGGER.warning('partner_id %s', self.partner_id)
        LOGGER.warning('flow_id %s', self.flow_id)
        ICPSudo = self.env['ir.config_parameter'].sudo()
        edi_directory = ICPSudo.get_param('edi.edi_root_directory', default='/EDI')
        root_path = os.path.join(os.sep, edi_directory, self.env.cr.dbname, str(self.partner_id.id), str(self.flow_id.id))
        LOGGER.warning('root_path %s', root_path)
        for attachment in self.edi_files:
            LOGGER.warning('- decode %s', base64.decodebytes(attachment.datas))
            LOGGER.warning('- display_name %s', attachment.display_name)
            self.write_in_file(root_path, attachment.display_name, base64.decodebytes(attachment.datas))
        self.env['edi.tools.edi.document.incoming'].import_process()
        
        return {'type': 'ir.actions.act_window_close'}


    def write_in_file(self, path, file_name, file_content):
        f = open('/'.join([path, file_name]), 'w+b')
        f.write(file_content)
        f.close()
        return '/'.join([path, file_name])