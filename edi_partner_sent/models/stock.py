from odoo import models, fields, api


class stock_picking(models.Model):
    _inherit = 'stock.picking'

    @api.multi
    def _function_partner_sent_get(self):
        edi_db = self.env['edi.tools.edi.document.outgoing']
        flow_db = self.env['edi.tools.edi.flow']
        flow_ids = flow_db.search([
            ('model', '=', 'stock.picking'),
            ('method', 'in', ['send_edi_export_essers','send_edi_export_vrd','send_edi_export_actius','send_edi_export_calwms'])
        ])
        for flow_id in flow_ids:
            for pick in self:
                edi_docs = edi_db.search([('flow_id', '=', flow_id.id), ('reference', '=', pick.name)])
                if not edi_docs:
                    continue
                edi_docs.sorted(key=lambda x: x.create_date, reverse=True)
                pick.partner_sent = edi_docs[0].create_date
        return pick.partner_sent



    partner_sent = fields.Datetime(compute='_function_partner_sent_get', string='Partner Sent', store='True')
