import copy
import datetime
from itertools import groupby
import json
import logging

from openerp import api, _
from openerp.osv import osv, fields
from openerp.exceptions import except_orm
from odoo.addons.edi_tools.models.edi_mixing import EDIMixin

_logger = logging.getLogger(__name__)

DESADV_LINE = {
    'lijnnummer': '',    #incrementing value
    'ean': '',           #stock.move:product_id -> product.product:barcode
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
        if len(record.order_reference) > 17:
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
            result = self.env['edi.tools.edi.document.outgoing'].create_from_content(picking.name, content, partner_id.id, 'stock.picking', 'send_edi_export_desadv_straight')
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

        co_id = 1
        so_id = self.env['sale.order'].search([('name', '=', delivery.origin)], limit=1).id
        if not so_id:
            raise osv.except_osv(_('Warning!'), _("Could not find matching sales order for an item in your selection!"))

        order = self.env['sale.order'].browse(so_id)
        company = self.env['res.company'].browse(co_id)
        now = datetime.datetime.now()

        # Basic header fields
        d = datetime.datetime.strptime(delivery.min_date, "%Y-%m-%d %H:%M:%S")

        edi_doc['message']['pakbonnummer'] = delivery.name
        edi_doc['message']['desadv_naam']      = delivery.name
        edi_doc['message']['leverplandatum']   = d.strftime("%Y%m%d%H%M%S")
        edi_doc['message']['berichtdatum'] = now.strftime("%Y%m%d%H%M%S")
        edi_doc['message']['klantreferentie'] = delivery.order_reference

        partner = self.env['res.partner'].browse(order[0].partner_id.id)
        if partner and partner.ref:
            partner_doc = copy.deepcopy(dict(DESADV_PARTY))
            partner_doc['qual'] = 'BY'
            partner_doc['gln']  = partner.ref
            edi_doc['message']['partys']['party'].append(partner_doc)

        if company:
            partner = self.env['res.partner'].browse(company.partner_id.id)
            if partner and partner.ref:
                partner_doc = copy.deepcopy(dict(DESADV_PARTY))
                partner_doc['qual'] = 'SU'
                partner_doc['gln']  = partner.ref
                edi_doc['message']['partys']['party'].append(partner_doc)

        partner = self.env['res.partner'].browse(delivery.partner_id.id)
        if partner and partner.ref:
            partner_doc = copy.deepcopy(dict(DESADV_PARTY))
            partner_doc['qual'] = 'DP'
            partner_doc['gln']  = partner.ref
            edi_doc['message']['partys']['party'].append(partner_doc)

        # Line items
        line_counter = 1
        for line in delivery.move_lines:
            product = self.env['product.product'].browse(line.product_id.id)
            edi_line = copy.deepcopy(dict(DESADV_LINE))
            edi_line['lijnnummer'] = line_counter
            edi_line['ean']        = product.barcode
            edi_line['aantal']     = int(line.product_uom_qty)

            line_counter = line_counter + 1
            edi_doc['message']['cpss']['cps']['lines']['line'].append(edi_line)

        # Return the result
        return edi_doc
