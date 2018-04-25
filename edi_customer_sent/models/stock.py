from odoo import models, fields, api


class stock_picking(models.Model):
    _inherit = "stock.picking"

    @api.multi
    def _function_customer_sent_get(self):
        edi_db = self.env['edi.tools.edi.document.outgoing']
        flow_db = self.env['edi.tools.edi.flow']
        flow_ids = flow_db.search([('model', '=', 'stock.picking'),
            ('method', 'in', ['send_edi_export_desadv_crossdock','send_edi_export_desadv_straight','send_edi_export_desadv_gamma'])
            ])
        for flow_id in flow_ids:
            for pick in self:
                edi_docs = edi_db.search([('flow_id', '=', flow_id), ('reference', 'in', [pick.name, pick.desadv_name])])
                if not edi_docs:
                    continue
                edi_docs.sorted(key=lambda x: x.create_date, reverse=True)
                pick.edi_docs = edi_docs[0].create_date


    customer_sent = fields.Datetime(compute='_function_customer_sent_get', string='Customer Sent')

