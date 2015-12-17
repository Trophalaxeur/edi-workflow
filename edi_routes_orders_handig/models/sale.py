from datetime import datetime, timedelta
from openerp import SUPERUSER_ID
from openerp import api, fields, models, _
from openerp.exceptions import UserError
from openerp.tools import float_is_zero, float_compare, DEFAULT_SERVER_DATETIME_FORMAT
from openerp.addons.edi import EDIMixin
from openerp.addons.edi_tools.models.exceptions import EdiValidationError
import openerp.addons.decimal_precision as dp
import logging
import json
_logger = logging.getLogger(__name__)


class SaleOrder(models.Model, EDIMixin):
    _inherit = "sale.order"

    @api.model
    def edi_import_orders_handig_validator(self, ids):
        _logger.debug("Validating handig order")

        # Read the EDI Document
        edi_db = self.env['edi.tools.edi.document.incoming']
        document = edi_db.browse(document_ids)
        document.ensure_one()

        try:
            data = json.loads(document.content)
            if not data:
                raise EdiValidationError('EDI Document is empty.')
        except Exception:
            raise EdiValidationError('Content is not valid JSON.')

        if not 'number' in data:
            raise EdiValidationError('Could not find field: number.')

        # If we get all the way to here, the document is valid
        return True

    @api.model
    def receive_edi_import_orders_handig(self, document_ids):
        document = self.env['edi.tools.edi.document.incoming'].browse(document_ids)
        document.ensure_one()
        return self.edi_import_orders_handig(document)

    @api.model
    def edi_import_orders_handig(self, document):
        data = json.loads(document.content)
        name = self.create_sale_order_handig(self, data)
        if not name:
            raise except_orm(_('No sales order created!'), _('Something went wrong while creating the sales order.'))
        edi_db = self.env['edi.tools.edi.document.incoming']
        edi_db.message_post(self, body='Sale order {!s} created'.format(name))
        return True

    @api.model
    def _build_party_header_handig(self, param, data):
        partner_db = self.env['res.partner']
        customer_address = data['billing_address']
        shipping_address = data['shipping_address']
        invoice_address = data['billing_address']

        param['partner_id'] = customer_address.id

            if party['qual'] == 'BY':
                pids = partner_db.search(cr, uid, [('ref', '=', party['gln'])])
                buyer = partner_db.browse(cr, uid, pids, context)[0]
                param['partner_id'] = buyer.id
                param['user_id'] = buyer.user_id.id
                param['fiscal_position'] = buyer.property_account_position.id
                param['payment_term'] = buyer.property_payment_term.id
                param['pricelist_id'] = buyer.property_product_pricelist.id
                fiscal_pos = self.pool.get('account.fiscal.position').browse(cr, uid, buyer.property_account_position.id) or False

            if party['qual'] == 'IV':
                pids = partner_db.search(cr, uid, [('ref', '=', party['gln'])])
                iv = partner_db.browse(cr, uid, pids, context)[0]
                param['partner_invoice_id'] = iv.id

            if party['qual'] == 'DP':
                pids = partner_db.search(cr, uid, [('ref', '=', party['gln'])])
                dp = partner_db.browse(cr, uid, pids, context)[0]
                param['partner_shipping_id'] = dp.id

        # if IV partner is not present invoice partner is
        #  - parent of BY or
        #  - BY

        if not param.get('partner_invoice_id', None):
            buyer = partner_db.browse(cr, uid, param['partner_id'], context)
            param['partner_invoice_id'] = buyer.id
            if buyer.parent_id:
                param['partner_invoice_id'] = buyer.parent_id.id

        if 'partner_shipping_id' not in param:
            param['partner_shipping_id'] = param['partner_id']

        return param

    @api.model
    def create_sale_order_handig(self, data):
        param = {}

        param = self._build_party_header_handig(param, data)
        param = self.create_sale_order(cr, uid, param, data, context)

        # Actually create the sale order
        sid = self.create(cr, uid, param, context=None)
        so = self.browse(cr, uid, [sid], context)[0]
        return so.name

    @api.model
    def create_sale_order(self, param, data):
        # Prepare the call to create a sale order
        param['origin'] = data['number']
        param['message_follower_ids'] = False
        param['categ_ids'] = False
        param['picking_policy'] = 'one'
        param['order_policy'] = 'picking'
        param['carrier_id'] = False
        param['invoice_quantity'] = 'order'
        param['client_order_ref'] = data['number']
        param['message_ids'] = False
        param['note'] = False
        param['project_id'] = False
        param['incoterm'] = False
        param['section_id'] = False
        fiscal_pos = self.pool.get('account.fiscal.position').browse(cr, uid, param['fiscal_position']) or False
        if 'user_id' not in param:
            param['user_id'] = uid
        elif not param['user_id']:
            param['user_id'] = uid

        # Create the line items
        pricelist_db = self.env['product.pricelist']
        param['order_line'] = []
        for line in data['line_items']:
            product = self.env['product.product'].search([('ean13', '=', line['product']['sku'])], limit=1)

            line_params = {
                'name' : product.name
                'property_ids'          : False
                'product_id'            : product.id
                'product_uom'           : product.uom_id.id
                'product_uos_qty'       : line['quantity']
                'product_uom_qty'       : line['quantity']
                'price_unit'            : line['price']
                'delay'                 : False
                'discount'              : False
                'address_allotment_id'  : False
                'type'                  : 'make_to_stock'
                'product_packaging'     : False
                'tax_id'                : [[6, False, self.env['account.fiscal.position'].map_tax(product.taxes_id).ids]]
            }

            param['order_line'].append(line_params)

        return param

    @api.model
    def resolve_customer_info(self, billing_address, shipping_address, email):

        partner_db = self.env['res.partner']
        country_db = self.evn['res.country']

        # Check if this partner already exists
        billing_partner = partner_db.search([('email', '=', email)])
        if billing_partner:
            billing_partner = partner_db.browse(billing_partner[0])

            # Check if the shipment address exists
            country_id = country_db.search([('code', '=', shipping_address['country'])])
            shipping_partner = False
            partner_ids = partner_db.search([('parent_id','=',billing_partner.id)])
            if partner_ids:
                for partner in partner_db.browse(cr, uid, partner_ids):
                    if partner.name == shipping_address['full_name'] and partner.city == shipping_address['city'] and partner.zip == shipping_address['zipcode'] and partner.street == shipping_address['address1'] and partner.street2 == shipping_address['address2'] and partner.country_id.id == country_id[0]:
                        shipping_partner = partner

            if shipping_partner:
                return billing_partner, shipping_partner

        # If the billing address doesn't exist yet, create it
        if not billing_partner:
            country_id = country_db.search([('code', '=', billing_address['country'])])
            vals = {
                'active'     : True,
                'customer'   : True,
                'is_company' : False,
                'city'       : billing_address['city'],
                'zip'        : billing_address['zipcode'],
                'street'     : billing_address['street'] + billing_address['house_number'] + billing_address['house_number_alt'],
                'country_id' : country_id[0],
                'email'      : email,
                'name'       : billing_address['firstname'] + billing_address['lastname']
            }

            billing_partner = partner_db.create(vals)
            billing_partner = partner_db.browse(billing_partner)

        # If the shipping address doesn't exist yet, create it
        country_id = country_db.search(cr, uid, [('code', '=', shipping_address['country']['iso'])])
        vals = {
                'active'     : True,
                'customer'   : True,
                'is_company' : False,
                'city'       : shipping_address['city'],
                'zip'        : shipping_address['zipcode'],
                'street'     : shipping_address['street'] + shipping_address['house_number'] + shipping_address['house_number_alt'],
                'country_id' : country_id[0],
                'email'      : email,
                'name'       : shipping_address['firstname'] + shipping_address['lastname']
        }

        shipping_partner = partner_db.create(vals)
        shipping_partner = partner_db.browse(shipping_partner)

        return billing_partner, shipping_partner
