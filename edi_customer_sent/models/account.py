from odoo import models, fields, api


class account_invoice(models.Model):
    _inherit = "account.invoice"

    @api.multi
    def _function_customer_sent_get(self):
        edi_db = self.env['edi.tools.edi.document.outgoing']
        flow_db = self.env['edi.tools.edi.flow']
        flow_id = flow_db.search([('model', '=', 'account.invoice'), ('method', '=', 'send_edi_export_invoic')], limit=1)
        for invoice in self:
            edi_docs = edi_db.search([('flow_id', '=', flow_id), ('reference', '=', invoice.number)])
            if not edi_docs:
                continue
            edi_docs.sorted(key=lambda x: x.create_date, reverse=True)
            invoice.customer_sent = edi_docs[0].create_date



    customer_sent = fields.Datetime(compute=_function_customer_sent_get, string='Customer Sent')
