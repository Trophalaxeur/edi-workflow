from openerp.osv import osv, fields


class account_invoice(osv.Model):
    _inherit = "account.invoice"

    def _account_invoice_from_edi_document(self, cr, uid, ids, context=None):
        result = []
        invoice_db = self.pool.get('account.invoice')
        for doc in self.pool.get('edi.tools.edi.document.outgoing').browse(cr, uid, ids, context=context):
            if doc.reference:
                invoice_ids = invoice_db.search(cr, uid, [('number', '=', doc.reference)])
                if invoice_ids:
                    result = result + invoice_ids
        return result

    def _function_customer_sent_get(self, cr, uid, ids, field, arg, context=None):
        edi_db = self.pool.get('edi.tools.edi.document.outgoing')
        flow_db = self.pool.get('edi.tools.edi.flow')
        flow_id = flow_db.search(cr, uid, [('model', '=', 'account.invoice'), ('method', '=', 'send_edi_export_invoic')])[0]
        res = dict.fromkeys(ids, False)
        for invoice in self.browse(cr, uid, ids, context=context):
            docids = edi_db.search(cr, uid, [('flow_id', '=', flow_id), ('reference', '=', invoice.number)])
            if not docids:
                continue
            edi_docs = edi_db.browse(cr, uid, docids, context=context)
            edi_docs.sorted(key=lambda x: x.create_date, reverse=True)
            res[invoice.id] = edi_docs[0].create_date
        return res

    _columns = {
        'customer_sent': fields.function(_function_customer_sent_get, type='datetime', string='Customer Sent',
                                         store={
                                             'edi.tools.edi.document.outgoing': (_account_invoice_from_edi_document, ['reference'], 10),
                                         }),
    }
