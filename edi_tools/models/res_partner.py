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
import logging
from odoo import models
from .edi_mixing import EDIMixin
from odoo import osv
_logger = logging.getLogger(__name__)

RES_PARTNER_EDI_STRUCT = {
    'name': True,
    'ref': True,
    'lang': True,
    'website': True,
    'email': True,
    'street': True,
    'street2': True,
    'zip': True,
    'city': True,
    'country_id': True,
    'state_id': True,
    'phone': True,
     #'fax': True,
    'mobile': True,
}

class res_partner(models.Model, EDIMixin):
    _inherit = "res.partner"

    def edi_export(self, records, edi_struct=None):
        return super(res_partner,self).edi_export(records,
                                                  edi_struct or dict(RES_PARTNER_EDI_STRUCT))

    def edi_import(self, edi_document):
        # handle bank info, if any
        edi_bank_ids = edi_document.pop('bank_ids', None)
        contact_id = super(res_partner,self).edi_import(edi_document)
        if edi_bank_ids:
            contact = self.browse(contact_id)
            import_ctx = dict((self.env.context or {}),
                              default_partner_id = contact.id)
            for ext_bank_id, bank_name in edi_bank_ids:
                try:
                    self.with_context(import_ctx).edi_import_relation('res.partner.bank',
                                             bank_name, ext_bank_id)
                except osv.osv.except_osv:
                    # failed to import it, try again with unrestricted default type
                    _logger.warning('Failed to import bank account using'
                                                                 'bank type: bank',
                                                                 exc_info=True)
        return contact_id


# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
