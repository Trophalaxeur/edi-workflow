import copy
import datetime
from itertools import groupby
import json
import logging

from openerp import api, _
from openerp.osv import osv, fields
from openerp.exceptions import except_orm
from openerp.addons.edi import EDIMixin

_logger = logging.getLogger(__name__)

DESADV_LINE = {
    'lijnnummer': '',    #incrementing value
    'ean': '',           #stock.move:product_id -> product.product:ean13
    'aantal': '',        #stock.move:product_qty
}

DESADV_PARTY = {
    'qual': '',
    'gln': '',
}

DESADV = {
    'message': {
        'desadv_naam': '',        #desadv_naam
        'berichtdatum': '',  # system date/time
        'pakbonnummer': '',  # stock.picking.out:name
        'leverplandatum': '',  # stock.picking.out:min_date
        'klantreferentie': '',  # stock.picking.out:order_reference
        'partys': {'party': []},  # partner details
        'cpss': {                #line items
            'cps': {
                'lines': {"line":[]},
            },
        },
    },
}


class stock_picking(osv.Model, EDIMixin):
    _inherit = "stock.picking"

    def _get_desadv_cps_segment(self):
        cps = {
            'pacs': {"pac": []},
            'lines': {"line": []},
        }
        return cps

    @api.model
    def valid_for_edi_export_desadv_straight(self, record):
        if record.state != 'done':
            return False
        return True

    @api.multi
    def send_edi_export_desadv_straight(self, partner_id):
        valid_pickings = self.filtered(self.valid_for_edi_export_desadv_straight)
        invalid_pickings = [p for p in self if p not in valid_pickings]
        if invalid_pickings:
            raise except_orm(_('Invalid pickings in selection!'), _('The following pickings are invalid, please remove from selection. %s') % (map(lambda record: record.name, invalid_pickings)))

        if len(set([p.desadv_name for p in valid_pickings])) > 1:
            raise except_orm(_('Invalid selection!'), _('The pickings you selected contain different desadv_name attribute values, please change the selection. %s') % (map(lambda record: (record.name, record.desadv_name), valid_pickings)))


        for picking in valid_pickings:
            content = picking.edi_export_desadv_straight(picking, edi_struct=None)
            result = self.env['edi.tools.edi.document.outgoing'].create_from_content(picking.name, content, partner_id.id, 'stock.picking', 'send_edi_export_vrd')
            if not result:
                raise except_orm(_('EDI creation failed!', _('EDI processing failed for the following picking %s') % (picking.name)))
        return True

    @api.model
    def edi_export_desadv_straight(self, delivery, edi_struct=None):
        edi_doc = copy.deepcopy(dict(DESADV))

        partner_db = self.pool.get('res.partner')
        order_db = self.pool.get('sale.order')
        company_db = self.pool.get('res.company')
        product_db = self.pool.get('product.product')

        co_id = company_db.search(cr, uid, [])[0]
        so_id = order_db.search(cr, uid, [('name', '=', delivery.origin)])
        if not so_id:
            raise osv.except_osv(_('Warning!'), _("Could not find matching sales order for an item in your selection!"))

        order = order_db.browse(cr, uid, so_id, context)[0]
        company = company_db.browse(cr, uid, co_id, context)
        now = datetime.datetime.now()

        # Basic header fields
        d = datetime.datetime.strptime(delivery.min_date, "%Y-%m-%d %H:%M:%S")

        edi_doc['message']['pakbonnummer'] = delivery.desadv_name
        edi_doc['message']['desadv_naam']      = delivery.desadv_name
        edi_doc['message']['berichtdatum'] = now.strftime("%Y%m%d%H%M%S")
        edi_doc['message']['klantreferentie'] = delivery.order_reference
        edi_doc['message']['orderdatum'] = d_order.strftime("%Y%m%d")

        if company:
            partner = partner_db.browse(cr, uid, company.partner_id.id, context)
            if partner and partner.ref:
                partner_doc = copy.deepcopy(dict(DESADV_PARTY))
                partner_doc['qual'] = 'SU'
                partner_doc['gln'] = partner.ref
                edi_doc['message']['partys']['party'].append(partner_doc)
                partner_doc = copy.deepcopy(dict(DESADV_PARTY))
                partner_doc['qual'] = 'SH'
                partner_doc['gln'] = partner.ref
                edi_doc['message']['partys']['party'].append(partner_doc)

        partner = partner_db.browse(cr, uid, delivery.partner_id.id, context)
        if partner and partner.ref:
            partner_doc = copy.deepcopy(dict(DESADV_PARTY))
            partner_doc['qual'] = 'DP'
            partner_doc['gln'] = partner.ref
            edi_doc['message']['partys']['party'].append(partner_doc)

        # Line items
        line_counter = 1
        for line in delivery.move_lines:
            product = product_db.browse(cr, uid, line.product_id.id, context)
            edi_line = copy.deepcopy(dict(DESADV_LINE))
            edi_line['lijnnummer'] = line_counter
            edi_line['ean']        = product.ean13
            edi_line['aantal']     = int(line.product_uom_qty)

            line_counter = line_counter + 1
            edi_doc['message']['cpss']['cps']['lines']['line'].append(edi_line)

        # Return the result
        return edi_doc
