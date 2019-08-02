import copy
import datetime
from dateutil.relativedelta import relativedelta
from itertools import groupby
import json
import logging

from openerp import models, fields, api, _
from openerp.osv import osv
from openerp.exceptions import except_orm
from openerp.addons.edi import EDIMixin
from openerp.addons.edi_tools.models.exceptions import EdiValidationError

import re

_logger = logging.getLogger(__name__)

class product_product(models.Model):
    _name = "product.product"
    _inherit = "product.product"
    product_eazy = fields.Selection([('Y', 'Yes'), ('N', 'No')], copy=False)

class stock_location(models.Model):
    _name = "stock.location"
    _inherit = "stock.location"
    eazystock_code = fields.Char(string="Eazystock Name")
    eazystock_enabled = fields.Boolean(string="Eazystock Active")
    eazystock_supplier = fields.Char(string="Eazystock Supplier Override")

class stock_picking(models.Model, EDIMixin):
    _inherit = "stock.picking"

    @api.model
    def valid_for_edi_export_stock_eazystock(self, record):
        return True

    @api.model
    def valid_for_edi_export_inbound_eazystock(self, record):
        return True

    @api.model
    def valid_for_edi_export_item_md_eazystock(self, record):
        return True

    @api.multi
    def send_edi_export_stock_eazystock(self, partner_id):
        valid_pickings = self.filtered(self.valid_for_edi_export_stock_eazystock)
        invalid_pickings = [p for p in self if p not in valid_pickings]
        if invalid_pickings:
            raise except_orm(_('Invalid pickings in selection!'), _('The following pickings are invalid, please remove from selection. %s') % (map(lambda record: record.name, invalid_pickings)))

        content = valid_pickings.edi_export_stock_eazystock(edi_struct=None)
        result = self.env['edi.tools.edi.document.outgoing'].create_from_content('Transactional_demand_Full_LUTEC-EU', content, partner_id.id, 'stock.picking', 'send_edi_export_stock_eazystock', type='EAZYSTOCK')
        if not result:
            raise except_orm(_('EDI creation failed!', _('EDI processing failed for the following picking %s') % (picking.name)))

        return result

    @api.multi
    def send_edi_export_stock_partial_eazystock(self, partner_id):
        valid_pickings = self.filtered(self.valid_for_edi_export_stock_eazystock)
        invalid_pickings = [p for p in self if p not in valid_pickings]
        if invalid_pickings:
            raise except_orm(_('Invalid pickings in selection!'), _('The following pickings are invalid, please remove from selection. %s') % (map(lambda record: record.name, invalid_pickings)))

        content = valid_pickings.edi_export_stock_partial_eazystock(edi_struct=None)
        result = self.env['edi.tools.edi.document.outgoing'].create_from_content('Transactional_demand_Partial_LUTEC-EU', content, partner_id.id, 'stock.picking', 'send_edi_export_stock_partial_eazystock', type='EAZYSTOCK')
        if not result:
            raise except_orm(_('EDI creation failed!', _('EDI processing failed for the following picking %s') % (picking.name)))

        return result

    @api.multi
    def send_edi_export_inbound_eazystock(self, partner_id):
        valid_pickings = self.filtered(self.valid_for_edi_export_inbound_eazystock)
        invalid_pickings = [p for p in self if p not in valid_pickings]
        if invalid_pickings:
            raise except_orm(_('Invalid pickings in selection!'), _('The following pickings are invalid, please remove from selection. %s') % (map(lambda record: record.name, invalid_pickings)))

        content = valid_pickings.edi_export_inbound_eazystock(edi_struct=None)
        result = self.env['edi.tools.edi.document.outgoing'].create_from_content('Purchase_order_Full_LUTEC-EU', content, partner_id.id, 'stock.picking', 'send_edi_export_inbound_eazystock', type='EAZYSTOCK')
        if not result:
            raise except_orm(_('EDI creation failed!', _('EDI processing failed for the following picking %s') % (picking.name)))

        return result

    @api.multi
    def send_edi_export_item_md_eazystock(self, partner_id):
        valid_products = self.filtered(self.valid_for_edi_export_item_md_eazystock)
        content = valid_products.edi_export_item_md_eazystock(edi_struct=None)
        result = self.env['edi.tools.edi.document.outgoing'].create_from_content('Item_Full_LUTEC-EU', content, partner_id.id, 'stock.picking', 'send_edi_export_item_md_eazystock', type='EAZYSTOCK')
        if not result:
            raise except_orm(_('EDI creation failed!', _('EDI processing failed for the following picking %s') % (picking.name)))

        return result

    @api.multi
    def edi_export_stock_eazystock(self, edi_struct=None):
        now = datetime.datetime.now()
        today = datetime.datetime.today()
        #pickings = self.env['stock.picking'].search([("state", "=", "done"),("picking_type_id", "=", 2),("date_done", ">=" , (today-relativedelta(days=7)).strftime("%Y%m%dT%H%M") )])
        pickings = self.env['stock.picking'].search([("state", "=", "done"),("picking_type_id", "=", 2)])
        edi_doc = ''
        for picking in pickings:
            #field definition
            linecounter = 1
            order = self.env['sale.order'].search([("name", "=", picking.origin)], limit=1)
            for move in picking.move_lines:
                if move.product_id and "SO" in str(picking.origin) and move.product_id.ean13:
                    transact_type = 'M'
                    item_code = str(move.product_id.name)
                    wh_code = str(move.location_id.eazystock_code) #stock.warehouse.code first part
                    if not wh_code:
                        wh_code = str(picking.picking_type_id.warehouse_id.code) #stock.warehouse.code first part
                    wh_group_code = 'LUTEC-EU'
                    so_ref = str(picking.origin)  #Sales Order Number
                    so_lineid = str(linecounter).zfill(3)
                    linecounter += 1
                    extract_date = str(now.strftime("%Y%m%dT%H%M"))
                    order_qty = str(int(move.product_uom_qty))
                    del_qty = str(int(move.product_uom_qty))
                    if order.requested_date :
                        req_date = str(order.requested_date)[0:4]+str(order.requested_date)[5:7]+str(order.requested_date)[8:10]
                    else :
                        _logger.info("No Order Req Date found : %s", str(order.name))
                        req_date = str(order.commitment_date)[0:4]+str(order.commitment_date)[5:7]+str(order.commitment_date)[8:10]
                    if picking.invoice_partner_id:
                        partner_name = picking.invoice_partner_id.name.encode('utf-8').strip() #change to short name, new field
                    else:
                        partner_name = ''
                    forecast = "Y"
                    service = "Y"
                    classify = "Y"
                    stockdate = ""
                    if order.client_order_ref:
                        free1 = order.client_order_ref.encode('utf-8').strip()
                    free2 = ""
                    #append lines
                    line_content = transact_type + '|' + item_code + '|' + wh_code + '|' + wh_group_code + '|' + so_ref + '|' + so_lineid + '|' + extract_date + '|' + order_qty + '|' + del_qty + '|' + req_date + '|' + partner_name + '|' + forecast + '|' + service + '|' + classify + '|' + stockdate + '|' + free1 + '|' + free2
                    edi_doc = edi_doc +line_content + '\r\n'
        
        #return consolidated result
        return edi_doc

    @api.multi
    def edi_export_stock_partial_eazystock(self, edi_struct=None):
        now = datetime.datetime.now()
        today = datetime.datetime.today()
        pickings = self.env['stock.picking'].search([("state", "=", "done"),("picking_type_id", "=", 2),("date_done", ">=" , (today-relativedelta(days=7)).strftime("%Y%m%dT%H%M") )])
        #pickings = self.env['stock.picking'].search([("state", "=", "done"),("picking_type_id", "=", 2)])
        edi_doc = ''
        for picking in pickings:
            #field definition
            linecounter = 1
            order = self.env['sale.order'].search([("name", "=", picking.origin)], limit=1)
            for move in picking.move_lines:
                if move.product_id and "SO" in str(picking.origin) and move.product_id.ean13:
                    transact_type = 'M'
                    item_code = str(move.product_id.name)
                    wh_code = str(move.location_id.eazystock_code) #stock.warehouse.code first part
                    if not wh_code:
                        wh_code = str(picking.picking_type_id.warehouse_id.code) #stock.warehouse.code first part
                    wh_group_code = 'LUTEC-EU'
                    so_ref = str(picking.origin)  #Sales Order Number
                    so_lineid = str(linecounter).zfill(3)
                    linecounter += 1
                    extract_date = str(now.strftime("%Y%m%dT%H%M"))
                    order_qty = str(int(move.product_uom_qty))
                    del_qty = str(int(move.product_uom_qty))
                    if order.requested_date :
                        req_date = str(order.requested_date)[0:4]+str(order.requested_date)[5:7]+str(order.requested_date)[8:10]
                    else :
                        _logger.info("No Order Req Date found : %s", str(order.name))
                        req_date = str(order.commitment_date)[0:4]+str(order.commitment_date)[5:7]+str(order.commitment_date)[8:10]
                    if picking.invoice_partner_id:
                        partner_name = picking.invoice_partner_id.name.encode('utf-8').strip() #change to short name, new field
                    else:
                        partner_name = ''
                    forecast = "Y"
                    service = "Y"
                    classify = "Y"
                    stockdate = ""
                    if order.client_order_ref:
                        free1 = order.client_order_ref.encode('utf-8').strip()
                    free2 = ""
                    #append lines
                    line_content = transact_type + '|' + item_code + '|' + wh_code + '|' + wh_group_code + '|' + so_ref + '|' + so_lineid + '|' + extract_date + '|' + order_qty + '|' + del_qty + '|' + req_date + '|' + partner_name + '|' + forecast + '|' + service + '|' + classify + '|' + stockdate + '|' + free1 + '|' + free2
                    edi_doc = edi_doc +line_content + '\r\n'
        
        #return consolidated result
        return edi_doc

    @api.multi
    def edi_export_inbound_eazystock(self, edi_struct=None):
        pickings = self.env['stock.picking'].search([("state", "=", "assigned"),("picking_type_id", "=", 1)]) #po state approved
        edi_doc = ''
        now = datetime.datetime.now()
        for picking in pickings:
            #field definition
            linecounter = 1
            po = self.env['purchase.order'].search([("name", "=", picking.origin)], limit=1)
            if not po:
                continue
            _logger.info("Picking : %s. PO %s.", str(picking.name), str(po.name))
            for move in picking.move_lines:
                if move.product_id and move.product_id.ean13 and "PO" in str(picking.origin):
                    transact_type = 'M'
                    item_code = str(move.product_id.name)
                    wh_code = str(picking.picking_type_id.warehouse_id.code)
                    wh_group_code = 'LUTEC-EU'
                    po_ref = str(picking.origin)  #Purchase Order Number
                    po_lineid = str(linecounter)
                    linecounter += 1
                    extract_date = str(now.strftime("%Y%m%dT%H%M"))
                    supplier = 'LUTEC' #to change : pick from product
                    order_qty = str(int(move.product_uom_qty))
                    if po.date_order:
                        _logger.info("Order Date found : %s", str(po.name))
                        order_date = po.date_order.encode('utf-8').strip()[0:4]+po.date_order.encode('utf-8').strip()[5:7]+po.date_order.encode('utf-8').strip()[8:10]
                    if po.minimum_planned_date :
                        req_date = str(po.minimum_planned_date)[0:4]+str(po.minimum_planned_date)[5:7]+str(po.minimum_planned_date)[8:10]
                    else :
                        _logger.info("No Order Req Date found : %s", str(po.name))
                        req_date = str(po.date_approve)[0:4]+str(po.date_approve)[5:7]+str(po.date_approve)[8:10]
                    del_qty = ''
                    rec_qty = ''
                    free1 = str(po.origin).encode('utf-8').strip()
                    free2 = ''
                    #append lines
                    line_content = transact_type + '|' + item_code + '|' + wh_code + '|' + wh_group_code + '|' + po_ref + '|' + po_lineid + '|' + extract_date + '|' + supplier + '|' + order_qty + '|' + order_date + '|' + req_date + '|' + del_qty + '|' + rec_qty + '|' + free1 + '|' + free2
                    edi_doc = edi_doc +line_content + '\r\n'
        
        #return consolidated result
        return edi_doc

    @api.multi
    def edi_export_item_md_eazystock(self, edi_struct=None):
        edi_doc = ''
        locations = self.env['stock.location'].search([("usage", "=", "internal"),("eazystock_enabled", "=", True)])
        products = self.env['product.product'].search([("type", "=", "product")])
        now = datetime.datetime.now()
        for product in products:
            if product.ean13:
                for location in locations:
                    current_location_stock = 0
                    quants =  self.env['stock.quant'].search([("location_id", "=", location.id),("product_id", "=", product.id)])
                    for quant in quants:
                        current_location_stock += quant.qty
                    #if current_location_stock == 0:
                    #    continue
                    transact_type = 'M' #1
                    #item_code = product.ean13.encode('utf-8').strip()
                    item_code = product.name.encode('utf-8').strip()
                    if location.eazystock_code:
                        wh_code = location.eazystock_code #3
                    else: 
                        wh_code = location.location_id.name
                    wh_group_code = 'LUTEC-EU'
                    extract_date = str(now.strftime("%Y%m%dT%H%M"))
                    #description = product.name.encode('utf-8').strip()
                    try:
                        description = str(product.description.encode('ascii'))
                    except:
                        description = product.name.encode('utf-8').strip()
                    itemcode2 = product.name.encode('utf-8').strip() #7
                    if location.eazystock_supplier:
                        pref_sup = location.eazystock_supplier
                    else:
                        pref_sup = 'LUTEC' #to change: from product md !!!
                    activ_date = str(product.create_date)[0:4]+str(product.create_date)[5:7]+str(product.create_date)[8:10]
                    if product.standard_price <= 0.0:
                        unit_cost = '0.01'
                    else:
                        unit_cost = str(product.standard_price)
                    unit_cost_currency = 'EUR' #11
                    buyer_code = 'LUTEC'
                    item_gr_1 = str(product.light_brand)
                    item_gr_2 = str(product.product_tmpl_id.categ_id.name)
                    uom = 'PCS' #15
                    pack_size = ''
                    if location.eazystock_code == 'ECW':
                        try:
                            lead_time = str(product.seller_ids[0].delay)
                        except:
                            lead_time = '99'
                    else:
                        lead_time = '1'
                    moq = '1' #18
                    maoq = '10000'
                    muoq = '1' #20
                    purchase_price = unit_cost #21
                    purchase_price_currency = 'EUR' #22
                    curr_stock = str(int(current_location_stock)).strip() #23
                    outstanding = '' #24
                    backorders = '' #25
                    transit_stock = '' #26
                    reserved = '' #27
                    replaced_item = '' #28
                    inherit_stock = '' #29
                    replace_mult = '' #30
                    free_1 = product.ean13.encode('utf-8').strip()
                    try:
                        free_2 = str(product.product_group.encode('ascii'))
                    except:
                        free_2 = ''
                    #last optional field #50 < add 18 line breaks
                    optionals = '||||||||||||||||||'
                    #append lines
                    _logger.info("product : %s location: %s quantity %s", item_code , wh_code, curr_stock)
                    try:
                        line_content = transact_type + '|' + item_code + '|' + wh_code + '|' + wh_group_code + '|' + extract_date + '|' + description + '|' + itemcode2 + '|' + pref_sup + '|' + activ_date + '|' + unit_cost + '|' + unit_cost_currency + '|' + buyer_code + '|' + item_gr_1 + '|' + item_gr_2 + '|' + uom + '|' + pack_size + '|' + lead_time + '|' + moq  + '|' + maoq + '|' + muoq + '|' + purchase_price + '|' + purchase_price_currency + '|' + curr_stock + '|' + outstanding + '|' + backorders  + '|' +  transit_stock  + '|' + reserved  + '|' + replaced_item + '|' + inherit_stock + '|' + replace_mult + '|' + free_1 + '|' + free_2 + optionals
                    except:
                        line_content = transact_type + '|' + item_code + '|' + wh_code + '|' + wh_group_code + '|' + extract_date + '|' + description + '|' + itemcode2 + '|' + pref_sup + '|' + activ_date + '|' + unit_cost + '|' + unit_cost_currency + '|' + buyer_code + '|' + item_gr_1 + '|' + item_gr_2 + '|' + uom + '|' + pack_size + '|' + lead_time + '|' + moq  + '|' + maoq + '|' + muoq + '|' + purchase_price + '|' + purchase_price_currency + '|' + curr_stock + '|' + outstanding + '|' + backorders  + '|' +  transit_stock  + '|' + reserved  + '|' + replaced_item + '|' + inherit_stock + '|' + replace_mult + '|' + free_1 + '||' + optionals
                    edi_doc = edi_doc +line_content + '\r\n'
        #return consolidated result
        return edi_doc

