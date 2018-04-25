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

from odoo import models

class res_company(models.Model):
    """Helper subclass for res.company providing util methods for working with
       companies in the context of EDI import/export. The res.company object
       itself is not EDI-exportable"""
    _inherit = "res.company"

    def edi_export_address(self, company, edi_address_struct=None):
        """Returns a dict representation of the address of the company record, suitable for
           inclusion in an EDI document, and matching the given edi_address_struct if provided.
           The first found address is returned, in order of preference: invoice, contact, default.

           :param browse_record company: company to export
           :return: dict containing the address representation for the company record, or
                    an empty dict if no address can be found
        """
        res_partner = self.env['res.partner']
        addresses = company.partner_id.address_get(['default', 'contact', 'invoice'])
        addr_id = addresses['invoice'] or addresses['contact'] or addresses['default']
        result = {}
        if addr_id:
            address = res_partner.browse(addr_id)
            result = res_partner.edi_export([address], edi_struct=edi_address_struct)[0]
        if company.logo:
            result['logo'] = company.logo.decode("utf-8") # already base64-encoded
        # if company.paypal_account:
        #     result['paypal_account'] = company.paypal_account
        # bank info: include only bank account supposed to be displayed in document footers
        res_partner_bank = self.env['res.partner.bank']
        bank_ids = res_partner_bank.search([('company_id','=',company.id)])
        if bank_ids:
            result['bank_ids'] = res_partner.edi_m2m(bank_ids)
        return result

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
