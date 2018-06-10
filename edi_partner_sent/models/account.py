from odoo import models, fields, api


class account_invoice(models.Model):
    _inherit = 'account.invoice'

    @api.multi
    def _function_partner_sent_get(self):
        edi_db = self.env['edi.tools.edi.document.outgoing']
        flow_db = self.env['edi.tools.edi.flow']
        flow_ids = flow_db.search([
            ('model', '=', 'account.invoice'),
            ('method', 'in', ['send_edi_export_invoice_targo'])
        ])
        for flow_id in flow_ids:
            for invoice in self:
                edi_docs = edi_db.search([('flow_id', '=', flow_id.id), ('reference', '=', invoice.number)])
                if not edi_docs:
                    continue
                edi_docs.sorted(key=lambda x: x.create_date, reverse=True)
                invoice.partner_sent = edi_docs[0].create_date
        return invoice.partner_sent



    partner_sent = fields.Datetime(string='Partner Sent')
