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
from .edi_mixing import EDIMixin

RES_CURRENCY_EDI_STRUCT = {
    # custom: 'code'
    'symbol': True,
    'rate': True,
}


class res_currency(models.Model, EDIMixin):
    _inherit = "res.currency"

    def edi_export(self, records, edi_struct=None):
        edi_struct = dict(edi_struct or RES_CURRENCY_EDI_STRUCT)
        edi_doc_list = []
        for currency in records:
            # Get EDI doc based on struct. The result will also contain all metadata fields and attachments.
            edi_doc = super(res_currency, self).edi_export([currency], edi_struct)[0]
            edi_doc.update(code=currency.name)
            edi_doc_list.append(edi_doc)
        return edi_doc_list

    def edi_import(self, edi_document):
        self._edi_requires_attributes(('code', 'symbol'), edi_document)
        external_id = edi_document['__id']
        existing_currency = self._edi_get_object_by_external_id(external_id, 'res_currency')
        if existing_currency:
            return existing_currency.id

        # find with unique ISO code
        existing_ids = self.search([('name', '=', edi_document['code'])])
        if existing_ids:
            return existing_ids[0].id

        # nothing found, create a new one
        currency_id = self.sudo().create({'name': edi_document['code'],
                                          'symbol': edi_document['symbol']})
        rate = edi_document.pop('rate')
        if rate:
            self.env['res.currency.rate'].sudo().create({'currency_id': currency_id, 'rate': rate})
        return currency_id

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
