# -*- coding: utf-8 -*-
##############################################################################
# For copyright and license notices, see __openerp__.py file in root directory
##############################################################################
from odoo import fields, models, api
import base64
import logging
LOGGER = logging.getLogger(__name__)

class EdifactSaleOrderImport(models.TransientModel):
    _name = 'edifact.sale.order.add.files'
    _description = 'Add sale orders to import list'

    edi_file = fields.Binary(string='EDI File', required=True)
    filename = fields.Char("File Name")

    def import_edi(self):
        self.env['edifact.document'].write_in_file('orders', self.filename, base64.decodebytes(self.edi_file))
        return {}

    # def action_import(self):
    #     edi_doc = self.env['edifact.document'].process_order_in_files()
    #     if not edi_doc:
    #         return
    #     value = {
    #         'view_type': 'form',
    #         'view_mode': 'form,tree',
    #         'res_model': 'edifact.document',
    #         'res_id': edi_doc.id,
    #         'type': 'ir.actions.act_window',
    #         'nodestroy': True
    #     }
    #     return value
