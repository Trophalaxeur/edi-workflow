from openerp.osv import osv, fields


class stock_picking(osv.Model):
    _inherit = "stock.picking"

    def _stock_picking_from_edi_document(self, cr, uid, ids, context=None):
        result = []
        picking_db = self.pool.get('stock.picking')
        for doc in self.pool.get('edi.tools.edi.document.outgoing').browse(cr, uid, ids, context=context):
            if doc.reference:
                picking_ids = picking_db.search(cr, uid, ['|', ('name', '=', doc.reference), ('desadv_name', '=', doc.reference)])
                if picking_ids:
                    result = result + picking_ids
        return result

    def _function_customer_sent_get(self, cr, uid, ids, field, arg, context=None):
        edi_db = self.pool.get('edi.tools.edi.document.outgoing')
        flow_db = self.pool.get('edi.tools.edi.flow')
        flow_ids = flow_db.search(cr, uid, [
            ('model', '=', 'stock.picking'),
            ('method', 'in', ['send_edi_export_desadv_crossdock','send_edi_export_desadv_straight','send_edi_export_desadv_gamma'])
            ])
        res = dict.fromkeys(ids, False)
        for flow_id in flow_ids:
            for pick in self.browse(cr, uid, ids, context=context):
                docids = edi_db.search(cr, uid, [('flow_id', '=', flow_id), ('reference', 'in', [pick.name, pick.desadv_name])])
                if not docids:
                    continue
                edi_docs = (edi_db.browse(cr, uid, docids, context=context))
                edi_docs.sorted(key=lambda x: x.create_date, reverse=True)
                res[pick.id] = edi_docs[0].create_date
        return res

    _columns = {
        'customer_sent': fields.function(_function_customer_sent_get, type='datetime', string='Customer Sent',
                                         store={
                                             'edi.tools.edi.document.outgoing': (_stock_picking_from_edi_document, ['reference'], 10),
                                         }),
    }
