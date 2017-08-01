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
        'desadv_naam': '',   #desadv_naam
        'berichtdatum': '',  # system date/time
        'orderdatum': '',  # SO date
        'pakbonnummer': '',  # stock.picking.out:name
        'leverplandatum': '',  # stock.picking.out:min_date
        'despatchdtm': '',  # stock.picking.out:date_done
        'klantreferentie': '',  # stock.picking.out:order_reference
        'incoterm': '', #stock.picking:incoterm
        'partys': {'party': []},  # partner details
        'cpss': {                #line items
            'cps': [],
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
    def valid_for_edi_export_desadv_gamma(self, record):
        if record.state != 'done':
            return False
        if len(record.order_reference) > 17:
            return False
        return True

    @api.multi
    def send_edi_export_desadv_gamma(self, partner_id):
        valid_pickings = self.filtered(self.valid_for_edi_export_desadv_gamma)
        invalid_pickings = [p for p in self if p not in valid_pickings]
        if invalid_pickings:
            raise except_orm(_('Invalid pickings in selection!'), _('The following pickings are invalid, please remove from selection. %s') % (map(lambda record: record.name, invalid_pickings)))

        if len(set([p.desadv_name for p in valid_pickings])) > 1:
            raise except_orm(_('Invalid selection!'), _('The pickings you selected contain different desadv_name attribute values, please change the selection. %s') % (map(lambda record: (record.name, record.desadv_name), valid_pickings)))


        for picking in valid_pickings:
            content = picking.edi_export_desadv_gamma(picking, edi_struct=None)
            result = self.env['edi.tools.edi.document.outgoing'].create_from_content(picking.name, content, partner_id.id, 'stock.picking', 'send_edi_export_desadv_gamma')
            if not result:
                raise except_orm(_('EDI creation failed!', _('EDI processing failed for the following picking %s') % (picking.name)))
        return True

    @api.model
    def edi_export_desadv_gamma(self, delivery, edi_struct=None):
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

        # partner = self.env['res.partner'].browse(order[0].partner_id.id)
        # if partner and partner.ref:
        #     partner_doc = copy.deepcopy(dict(DESADV_PARTY))
        #     partner_doc['qual'] = 'BY'
        #     partner_doc['gln']  = partner.ref
        #     edi_doc['message']['partys']['party'].append(partner_doc)
        if company:
            partner = self.env['res.partner'].browse(company.partner_id.id)
            if partner and partner.ref:
                partner_doc = copy.deepcopy(dict(DESADV_PARTY))
                partner_doc['qual'] = 'SU'
                partner_doc['gln']  = partner.ref
                partner_doc['vatnum'] = partner.vat.replace(" ","")
                edi_doc['message']['partys']['party'].append(partner_doc)
                partner_doc = copy.deepcopy(dict(DESADV_PARTY))
                partner_doc['qual'] = 'SH'
                partner_doc['gln'] = partner.ref
                edi_doc['message']['partys']['party'].append(partner_doc)
        
        partner = self.env['res.partner'].browse(delivery.sale_partner_id.id)
        #if partner and partner.ref and (partner.parent_id.vat == 'NL005681108B01' or partner.vat == 'NL005681108B01' or partner.vat == 'IT05602710963'):
        if partner and partner.ref and (any(taxcode in ('NL005681108B01','IT05602710963') for taxcode in (partner.parent_id.vat,partner.vat))):
            _logger.debug("GAMMA!")
            partner_doc = copy.deepcopy(dict(DESADV_PARTY))
            partner_doc['qual'] = 'BY'
            partner_doc['gln'] = partner.ref
            edi_doc['message']['partys']['party'].append(partner_doc)
            # if instruction 2 == starts with XDCK > UC == sale_partner_id
            partner_doc = copy.deepcopy(dict(DESADV_PARTY))
            partner_doc['qual'] = 'UC'
            partner_doc['gln'] = partner.ref
            edi_doc['message']['partys']['party'].append(partner_doc)

        partner = self.env['res.partner'].browse(delivery.partner_id.id)
        if partner and partner.ref:
            partner_doc = copy.deepcopy(dict(DESADV_PARTY))
            partner_doc['qual'] = 'DP'
            partner_doc['gln']  = partner.ref
            edi_doc['message']['partys']['party'].append(partner_doc)

        if delivery.incoterm.id == 1:
            edi_doc['message']['incoterm'] = "4"

        #OUT/060314 > 3 lijnen , 4 quants, 1 pack : 542006040000659821

        # Get trackings from all delivery lines without duplicates
        trackings = []
        for operation in delivery.pack_operation_ids:
            if operation.result_package_id:
                trackings.append(operation.result_package_id)
            else:
                raise osv.except_osv(_('Warning!'), _("There is a line without SSCC number (pack) {!s}").format(operation))
        trackings = set(trackings)  # remove duplicates
        
        def find_root(element):
            if element.parent_id:
                return find_root(element.parent_id)
            else:
                return element

        # find all root trackings
        #tracking_roots = map(find_root, trackings)
        #tracking_roots = set(tracking_roots)
        
        tracking_roots = trackings

        def traverse(node, parent_node=None):
            yield node, parent_node
            for child in node.children_ids:
                for r1, r2 in traverse(child, node):
                    yield r1, r2

        def _build_cps_for_tracking(tracking, parent_cps_counter=None, line_counter=1):
            cps_segment = {
                "line": cps_counter,
                "pacs": {
                    "pac": []
                },
                "lines": {
                    "line": []
                }
            }
            if parent_cps_counter:
                cps_segment["subline"] = parent_cps_counter

            # only one tracking per cps segment
            tracking_segment = {}
            tracking_segment["iso"] = tracking.ul_id.name  # pallet | box
            tracking_segment["children"] = 0
            for child in tracking.children_ids:
                tracking_segment["children"] = 1
            tracking_segment["sscc"] = tracking.name
            tracking_segment["qua"] = 1
            tracking_segment["brutweight"] = tracking.weight
            cps_segment["pacs"]["pac"].append(tracking_segment)
            #quant is gesorteerd op ID
            #dit is niet altijd correct, moet op picking volgorde zijn volgens LINE ID van Essers PCLO 
            for quant in tracking.quant_ids:
                line_segment = {}
                product = self.env['product.product'].browse(quant.product_id.id)
                sorted_history_ids = sorted(quant.history_ids, key=lambda move: move.date, reverse=True)
                order_origin = sorted_history_ids[0].picking_id[0].origin
                #so_ids = order_db.search(cr, uid, [('name', '=', order_origin)]) #was origin, nog available on quant
                #so_ids = self.env['sale.order'].search([('name', '=', delivery.origin)], limit=1).id
                so_ids = so_id
                if not so_ids:
                    raise osv.except_orm(_('Error!'), _("No sales order found for origin \"%s\" via quant (%d)" % (order_origin, quant.id)))
                order = self.env['sale.order'].browse(so_id)
                dtm = datetime.datetime.strptime(order.date_order, "%Y-%m-%d %H:%M:%S")

                if product.bom_ids and order.order_bomified:
                    _logger.info("bomified order with bom product, appending bom components to EDI doc")
                    for bom in product.bom_ids[0].bom_line_ids:
                        bomproduct = self.env['product.product'].browse(bom.product_id.id)
                        line_segment = {}
                        line_segment["num"] = line_counter
                        line_segment["suart"] = bomproduct.name
                        line_segment["desc"] = bomproduct.description[:35]
                        line_segment["gtin"] = bomproduct.ean13
                        line_segment["delqua"] = int(quant.qty)*int(bom.product_qty)
                        line_segment["ucgln"] = order.partner_id.ref
                        line_segment["ucorder"] = order.origin
                        line_segment["ucorderdate"] = dtm.strftime("%Y%m%d")
                        cps_segment["lines"]["line"].append(line_segment)
                        line_counter += 1
                else:
                    _logger.info("no bom product or no bomified order, appending product to EDI doc")
                    line_segment["num"] = line_counter
                    line_segment["suart"] = product.name
                    line_segment["desc"] = product.description[:35]
                    line_segment["gtin"] = product.ean13
                    line_segment["delqua"] = int(quant.qty)
                    line_segment["ucgln"] = order.partner_id.ref
                    line_segment["ucorder"] = order.origin
                    line_segment["ucorderdate"] = dtm.strftime("%Y%m%d")
                    cps_segment["lines"]["line"].append(line_segment)
                    line_counter += 1

            if not cps_segment["lines"]["line"]:
                cps_segment.pop("lines")
            return cps_segment, line_counter

        number_of_packs = 0
        weight_of_packs = 0
        cps_counter = 1
        line_counter = 1

        # create a root element to hold everything together
        header_cps_segment = {
            "line": cps_counter,
            "pacs": {
                "pac": []
            }
        }
        # append to the edi document
        edi_doc["message"]["cpss"]["cps"].append(header_cps_segment)
        cps_counter += 1

        cps_dictionary = {}
        for tracking in tracking_roots:
            for node, parent_node in traverse(tracking):
                if parent_node:
                    cps_segment, line_counter = _build_cps_for_tracking(node, cps_dictionary[parent_node.id]["line"], line_counter=line_counter)
                else:
                    cps_segment, line_counter = _build_cps_for_tracking(node, 1, line_counter=line_counter)
                cps_dictionary[node.id] = cps_segment
                edi_doc["message"]["cpss"]["cps"].append(cps_segment)
                cps_counter += 1

        # iterate over all cps segments to calculate pallet weight and count
        for cps in edi_doc["message"]["cpss"]["cps"]:
            if not cps["pacs"]["pac"]:
                continue
            pac = cps["pacs"]["pac"][0]
            if "Box" in pac["iso"]:
                _logger.debug("Box found, added to count")
                number_of_packs +=1
                weight_of_packs += pac["brutweight"]
            if "Pallet" in pac["iso"] and int(pac["children"]) == 0:
                _logger.debug("Pallet found without children, added to count")
                number_of_packs +=1
                weight_of_packs += pac["brutweight"]



        # add total weight of pallets and count of pallets to the first segment
        header_cps_segment["pacs"]["pac"].append({
            "totbrutweight": int(weight_of_packs),
            "qua": int(number_of_packs),
            "iso": "sum"
        })

        # Return the result
        return edi_doc
