import copy
import datetime
from itertools import groupby
import json
import logging

from odoo import api, _, models
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

class stock_picking(models.Model, EDIMixin):
    _inherit = "stock.picking"

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
        if order.order_bomified:
            for line in delivery.move_lines:
                if not line.product_id.bom_ids:
                    _logger.info("no bom product, appending product to EDI doc")
                    product = self.env['product.product'].browse(line.product_id.id)
                    edi_line = copy.deepcopy(dict(DESADV_LINE))
                    edi_line['lijnnummer'] = line_counter
                    edi_line['ean']        = product.barcode
                    edi_line['aantal']     = int(line.product_uom_qty)
                    line_counter = line_counter + 1
                    edi_doc['message']['cpss']['cps']['lines']['line'].append(edi_line)
                else:
                    _logger.info("bom product in bomified order, appending components to EDI doc")
                    for bom in line.product_id.bom_ids[0].bom_line_ids:
                        product = self.env['product.product'].browse(bom.product_id.id)
                        edi_line = copy.deepcopy(dict(DESADV_LINE))
                        edi_line['lijnnummer'] = line_counter
                        edi_line['ean']        = product.barcode
                        edi_line['aantal']     = int(line.product_uom_qty)*int(bom.product_qty)
                        line_counter = line_counter + 1
                        edi_doc['message']['cpss']['cps']['lines']['line'].append(edi_line)

        else:
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
