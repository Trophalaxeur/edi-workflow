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
from odoo import models, fields
from .edi_mixing import EDIMixin
from werkzeug import url_encode

INVOICE_LINE_EDI_STRUCT = {
    'name': True,
    'origin': True,
    'uom_id': True,
    'product_id': True,
    'price_unit': True,
    'quantity': True,
    'discount': True,

    # fields used for web preview only - discarded on import
    'price_subtotal': True,
}

INVOICE_TAX_LINE_EDI_STRUCT = {
    'name': True,
    'base': True,
    'amount': True,
    'manual': True,
    'sequence': True,
    'base_amount': True,
    'tax_amount': True,
}

INVOICE_EDI_STRUCT = {
    'name': True,
    'origin': True,
    'company_id': True, # -> to be changed into partner
    'type': True, # -> reversed at import
    'internal_number': True, # -> reference at import
    'comment': True,
    'date_invoice': True,
    'date_due': True,
    'partner_id': True,
    'payment_term': True,
    #custom: currency_id
    'invoice_line': INVOICE_LINE_EDI_STRUCT,
    'tax_line': INVOICE_TAX_LINE_EDI_STRUCT,

    # fields used for web preview only - discarded on import
    #custom: 'partner_ref'
    'amount_total': True,
    'amount_untaxed': True,
    'amount_tax': True,
}

class account_invoice(models.Model, EDIMixin):
    _inherit = 'account.move'

    def edi_export(self, records, edi_struct=None):
        """Exports a supplier or customer invoice"""
        edi_struct = dict(edi_struct or INVOICE_EDI_STRUCT)
        res_company = self.env['res.company']
        res_partner = self.env['res.partner']
        edi_doc_list = []
        for invoice in records:
            # generate the main report
            self._edi_generate_report_attachment(invoice)
            edi_doc = super(account_invoice,self).edi_export([invoice], edi_struct)[0]
            edi_doc.update({
                    'company_address': res_company.edi_export_address(invoice.company_id),
                    #'company_paypal_account': invoice.company_id.paypal_account,
                    'partner_address': res_partner.edi_export([invoice.partner_id])[0],
                    'currency': self.pool.get('res.currency').edi_export([invoice.currency_id])[0],
                    'partner_ref': invoice.reference or False,
            })
            edi_doc_list.append(edi_doc)
        return edi_doc_list

    def _edi_tax_account(self, invoice_type='out_invoice'):
        #TODO/FIXME: should select proper Tax Account
        account_pool = self.env['account.account']
        account_ids = account_pool.search([('type','<>','view'),('type','<>','income'), ('type', '<>', 'closed')])
        tax_account = False
        if account_ids:
            tax_account = account_ids[0].id
        return tax_account

    def _edi_invoice_account(self, partner_id, invoice_type):
        res_partner = self.env['res.partner']
        partner = res_partner.browse(partner_id)
        if invoice_type in ('out_invoice', 'out_refund'):
            invoice_account = partner.property_account_receivable
        else:
            invoice_account = partner.property_account_payable
        return invoice_account

    def _edi_product_account(self, product_id, invoice_type):
        product_pool = self.env['product.product']
        product = product_pool.browse(product_id)
        if invoice_type in ('out_invoice','out_refund'):
            account = product.property_account_income or product.categ_id.property_account_income_categ
        else:
            account = product.property_account_expense or product.categ_id.property_account_expense_categ
        return account

    def _edi_import_company(self, edi_document):
        # TODO: for multi-company setups, we currently import the document in the
        #       user's current company, but we should perhaps foresee a way to select
        #       the desired company among the user's allowed companies

        self._edi_requires_attributes(('company_id','company_address','type'), edi_document)
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

        invoice_type = edi_document['type']
        if invoice_type.startswith('out_'):
            company_address_edi['customer'] = True
        else:
            company_address_edi['supplier'] = True
        partner_id = res_partner.edi_import(company_address_edi)
        # modify edi_document to refer to new partner
        partner = res_partner.browse(partner_id)
        partner_edi_m2o = self.edi_m2o(partner)
        edi_document['partner_id'] = partner_edi_m2o
        edi_document.pop('partner_address', None) # ignored, that's supposed to be our own address!

        return partner_id

    def edi_import(self, edi_document):
        """ During import, invoices will import the company that is provided in the invoice as
            a new partner (e.g. supplier company for a customer invoice will be come a supplier
            record for the new invoice.
            Summary of tasks that need to be done:
                - import company as a new partner, if type==in then supplier=1, else customer=1
                - partner_id field is modified to point to the new partner
                - company_address data used to add address to new partner
                - change type: out_invoice'<->'in_invoice','out_refund'<->'in_refund'
                - reference: should contain the value of the 'internal_number'
                - reference_type: 'none'
                - internal number: reset to False, auto-generated
                - journal_id: should be selected based on type: simply put the 'type'
                    in the context when calling create(), will be selected correctly
                - payment_term: if set, create a default one based on name...
                - for invoice lines, the account_id value should be taken from the
                    product's default, i.e. from the default category, as it will not
                    be provided.
                - for tax lines, we disconnect from the invoice.line, so all tax lines
                    will be of type 'manual', and default accounts should be picked based
                    on the tax config of the DB where it is imported.
        """
        self._edi_requires_attributes(('company_id','company_address','type','invoice_line','currency'), edi_document)

        # extract currency info
        res_currency = self.env['res.currency']
        currency_info = edi_document.pop('currency')
        currency_id = res_currency.edi_import(currency_info)
        currency = res_currency.browse(currency_id)
        edi_document['currency_id'] =  self.edi_m2o(currency)
        # change type: out_invoice'<->'in_invoice','out_refund'<->'in_refund'
        invoice_type = edi_document['type']
        invoice_type = invoice_type.startswith('in_') and invoice_type.replace('in_','out_') or invoice_type.replace('out_','in_')
        edi_document['type'] = invoice_type

        # import company as a new partner
        partner_id = self._edi_import_company(edi_document)

        # Set Account
        invoice_account = self._edi_invoice_account(partner_id, invoice_type)
        edi_document['account_id'] = invoice_account and self.edi_m2o(invoice_account) or False

        # reference: should contain the value of the 'internal_number'
        edi_document['reference'] = edi_document.get('internal_number', False)
        # reference_type: 'none'
        edi_document['reference_type'] = 'none'

        # internal number: reset to False, auto-generated
        edi_document['internal_number'] = False

        # discard web preview fields, if present
        edi_document.pop('partner_ref', None)

        # journal_id: should be selected based on type: simply put the 'type' in the context when calling create(), will be selected correctly
        context = dict(self.env.context, type=invoice_type)

        # for invoice lines, the account_id value should be taken from the product's default, i.e. from the default category, as it will not be provided.
        for edi_invoice_line in edi_document['invoice_line']:
            product_info = edi_invoice_line['product_id']
            product_id = self.with_context(context).edi_import_relation('product.product', product_info[1],
                                                  product_info[0])
            account = self.with_context(context)._edi_product_account(product_id, invoice_type)
            # TODO: could be improved with fiscal positions perhaps
            # account = fpos_obj.map_account(cr, uid, fiscal_position_id, account.id)
            edi_invoice_line['account_id'] = self.with_context(context).edi_m2o(cr, uid, account, context=context) if account else False

            # discard web preview fields, if present
            edi_invoice_line.pop('price_subtotal', None)

        # for tax lines, we disconnect from the invoice.line, so all tax lines will be of type 'manual', and default accounts should be picked based
        # on the tax config of the DB where it is imported.
        tax_account = self.with_context(context)._edi_tax_account()
        tax_account_info = self.with_context(context).edi_m2o(tax_account)
        for edi_tax_line in edi_document.get('tax_line', []):
            edi_tax_line['account_id'] = tax_account_info
            edi_tax_line['manual'] = True

        return super(account_invoice,self).edi_import(edi_document)


    def _edi_record_display_action(self, id, context=None):
        """Returns an appropriate action definition dict for displaying
           the record with ID ``rec_id``.

           :param int id: database ID of record to display
           :return: action definition dict
        """
        action = super(account_invoice,self)._edi_record_display_action(id)
        try:
            invoice = self.browse(id)
            if 'out_' in invoice.type:
                view_ext_id = 'invoice_form'
                journal_type = 'sale'
            else:
                view_ext_id = 'invoice_supplier_form'
                journal_type = 'purchase'
            ctx = "{'type': '%s', 'journal_type': '%s'}" % (invoice.type, journal_type)
            action.update(context=ctx)
            view_id = self.env['ir.model.data'].get_object_reference('account', view_ext_id)[1]
            action.update(views=[(view_id,'form'), (False, 'tree')])
        except ValueError:
            # ignore if views are missing
            pass
        return action

    # def _edi_paypal_url(self, cr, uid, ids, field, arg, context=None):
    #     res = dict.fromkeys(ids, False)
    #     for inv in self.browse(cr, uid, ids, context=context):
    #         if inv.type == 'out_invoice' and inv.company_id.paypal_account:
    #             params = {
    #                 "cmd": "_xclick",
    #                 "business": inv.company_id.paypal_account,
    #                 "item_name": "%s Invoice %s" % (inv.company_id.name, inv.number or ''),
    #                 "invoice": inv.number,
    #                 "amount": inv.residual,
    #                 "currency_code": inv.currency_id.name,
    #                 "button_subtype": "services",
    #                 "no_note": "1",
    #                 "bn": "OpenERP_Invoice_PayNow_" + inv.currency_id.name,
    #             }
    #             res[inv.id] = "https://www.paypal.com/cgi-bin/webscr?" + url_encode(params)
    #     return res
    #
    # _columns = {
    #     'paypal_url': fields.function(_edi_paypal_url, type='char', string='Paypal Url'),
    # }


class account_invoice_line(models.Model, EDIMixin):
    _inherit='account.move.line'

class account_invoice_tax(models.Model, EDIMixin):
    _inherit = "account.move.tax"



# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
