# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Business Applications
#    Copyright (c) 2011-2012 OpenERP S.A. <http://openerp.com>
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################
from odoo import models, fields, api
from .edi_mixing import EDIMixin

SALE_ORDER_LINE_EDI_STRUCT = {
    'sequence': True,
    'name': True,
    # custom: 'date_planned'
    'product_id': True,
    'product_uom': True,
    'price_unit': True,
    # custom: 'product_qty'
    'discount': True,

    # fields used for web preview only - discarded on import
    'price_subtotal': True,
}

SALE_ORDER_EDI_STRUCT = {
    'name': True,
    'origin': True,
    'company_id': True,  # -> to be changed into partner
    # custom: 'partner_ref'
    'date_order': True,
    'partner_id': True,
    # custom: 'partner_address'
    # custom: 'notes'
    'order_line': SALE_ORDER_LINE_EDI_STRUCT,

    # fields used for web preview only - discarded on import
    'amount_total': True,
    'amount_untaxed': True,
    'amount_tax': True,
    'payment_term_id': True,
    # 'order_policy': True,
    'user_id': True,
    'state': True,
}


class sale_order(models.Model, EDIMixin):
    _inherit = 'sale.order'

    @api.model
    def edi_export(self, records, edi_struct=None):
        """Exports a Sale order"""
        edi_struct = dict(edi_struct or SALE_ORDER_EDI_STRUCT)
        res_company = self.env['res.company']
        res_partner_obj = self.env['res.partner']
        edi_doc_list = []
        for order in records:
            # generate the main report
            self._edi_generate_report_attachment(order)

            # Get EDI doc based on struct. The result will also contain all metadata fields and attachments.
            edi_doc = super(sale_order, self).edi_export([order], edi_struct)[0]
            edi_doc.update({
                # force trans-typing to purchase.order upon import
                '__import_model': 'purchase.order',
                '__import_module': 'purchase',

                'company_address': res_company.edi_export_address(order.company_id),
                'partner_address': res_partner_obj.edi_export([order.partner_id])[0],

                'currency': self.env['res.currency'].edi_export([order.pricelist_id.currency_id])[0],
                'partner_ref': order.client_order_ref or False,
                'notes': order.note or False,
            })
            edi_doc_list.append(edi_doc)
        return edi_doc_list

    def _edi_import_company(self, edi_document):
        # TODO: for multi-company setups, we currently import the document in the
        #       user's current company, but we should perhaps foresee a way to select
        #       the desired company among the user's allowed companies

        self._edi_requires_attributes(('company_id', 'company_address'), edi_document)
        res_partner = self.env['res.partner']

        xid, company_name = edi_document.pop('company_id')
        # Retrofit address info into a unified partner info (changed in v7 - used to keep them separate)
        company_address_edi = edi_document.pop('company_address')
        company_address_edi['name'] = company_name
        company_address_edi['is_company'] = True
        company_address_edi['__import_model'] = 'res.partner'
        company_address_edi['__id'] = xid  # override address ID, as of v7 they should be the same anyway
        if company_address_edi.get('logo'):
            company_address_edi['image'] = company_address_edi.pop('logo')
        company_address_edi['customer'] = True
        partner_id = res_partner.edi_import(company_address_edi)

        # modify edi_document to refer to new partner
        partner = res_partner.browse(partner_id)
        partner_edi_m2o = self.edi_m2o(partner)
        edi_document['partner_id'] = partner_edi_m2o
        edi_document['partner_invoice_id'] = partner_edi_m2o
        edi_document['partner_shipping_id'] = partner_edi_m2o

        edi_document.pop('partner_address', None)  # ignored, that's supposed to be our own address!
        return partner_id

    def _edi_get_pricelist(self, partner_id, currency):
        # TODO: refactor into common place for purchase/sale, e.g. into product module
        partner_model = self.env['res.partner']
        partner = partner_model.browse(partner_id)
        pricelist = partner.property_product_pricelist
        if not pricelist:
            pricelist = self.env['ir.model.data'].get_object('product', 'list0')
        if not pricelist.currency_id == currency:
            # look for a pricelist with the right type and currency, or make a new one
            product_pricelist = self.env['product.pricelist']
            match_pricelist_ids = product_pricelist.search([('currency_id', '=', currency.id)])
            if match_pricelist_ids:
                pricelist_id = match_pricelist_ids[0]
            else:
                pricelist_name = _('EDI Pricelist (%s)') % (currency.name,)
                pricelist_id = product_pricelist.create({'name': pricelist_name,
                                                         'currency_id': currency.id})
            pricelist = pricelist_id
        return self.edi_m2o(pricelist)

    def edi_import(self, edi_document):
        self._edi_requires_attributes(('company_id', 'company_address', 'order_line', 'date_order', 'currency'),
                                      edi_document)

        # import company as a new partner
        partner_id = self._edi_import_company(edi_document)

        # currency for rounding the discount calculations and for the pricelist
        res_currency = self.env['res.currency']
        currency_info = edi_document.pop('currency')
        currency_id = res_currency.edi_import(currency_info)
        order_currency = res_currency.browse(currency_id)

        partner_ref = edi_document.pop('partner_ref', False)
        edi_document['client_order_ref'] = edi_document['name']
        edi_document['name'] = partner_ref or edi_document['name']
        edi_document['note'] = edi_document.pop('notes', False)
        edi_document['pricelist_id'] = self._edi_get_pricelist(partner_id, order_currency)

        # discard web preview fields, if present
        edi_document.pop('amount_total', None)
        edi_document.pop('amount_tax', None)
        edi_document.pop('amount_untaxed', None)

        order_lines = edi_document['order_line']
        for order_line in order_lines:
            self._edi_requires_attributes(('product_id', 'product_uom', 'product_qty', 'price_unit'), order_line)
            order_line['product_uom_qty'] = order_line['product_qty']
            del order_line['product_qty']

            # discard web preview fields, if present
            order_line.pop('price_subtotal', None)
        return super(sale_order, self).edi_import(edi_document)

    # def _edi_paypal_url(self, cr, uid, ids, field, arg, context=None):
    #     res = dict.fromkeys(ids, False)
    #     for order in self.browse(cr, uid, ids, context=context):
    #         if order.order_policy in ('prepaid', 'manual') and \
    #                 order.company_id.paypal_account and order.state != 'draft':
    #             params = {
    #                 "cmd": "_xclick",
    #                 "business": order.company_id.paypal_account,
    #                 "item_name": order.company_id.name + " Order " + order.name,
    #                 "invoice": order.name,
    #                 "amount": order.amount_total,
    #                 "currency_code": order.pricelist_id.currency_id.name,
    #                 "button_subtype": "services",
    #                 "no_note": "1",
    #                 "bn": "OpenERP_Order_PayNow_" + order.pricelist_id.currency_id.name,
    #             }
    #             res[order.id] = "https://www.paypal.com/cgi-bin/webscr?" + url_encode(params)
    #     return res

    # _columns = {
    #     'paypal_url': fields.function(_edi_paypal_url, type='char', string='Paypal Url'),
    # }


class sale_order_line(models.Model, EDIMixin):
    _inherit = 'sale.order.line'

    def edi_export(self, records, edi_struct=None, context=None):
        """Overridden to provide sale order line fields with the expected names
           (sale and purchase orders have different column names)"""
        edi_struct = dict(edi_struct or SALE_ORDER_LINE_EDI_STRUCT)
        edi_doc_list = []
        for line in records:
            edi_doc = super(sale_order_line, self).edi_export([line], edi_struct)[0]
            edi_doc['__import_model'] = 'purchase.order.line'
            edi_doc['product_qty'] = line.product_uom_qty
            # if line.product_uos:
            #     edi_doc.update(product_uom=line.product_uos,
            #                    product_qty=line.product_uos_qty)
            edi_doc_list.append(edi_doc)
        return edi_doc_list

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
