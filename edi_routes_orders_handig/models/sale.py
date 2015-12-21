from datetime import datetime, timedelta
from openerp import SUPERUSER_ID
from openerp import api, fields, models, _
from openerp.exceptions import UserError
from openerp.tools import float_is_zero, float_compare, DEFAULT_SERVER_DATETIME_FORMAT
from openerp.addons.edi_tools.models.exceptions import EdiValidationError
import openerp.addons.decimal_precision as dp
import logging
import json
_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _inherit = "sale.order"

    @api.model
    def edi_import_orders_handig_validator(self, ids):
        _logger.debug("Validating handig order")

        # Read the EDI Document
        edi_db = self.env['edi.tools.edi.document.incoming']
        document = edi_db.browse(ids)
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
    def receive_edi_import_orders_handig(self, document_id):
        document = self.env['edi.tools.edi.document.incoming'].browse(document_id)
        document.ensure_one()
        return self.edi_import_orders_handig(document)

    @api.model
    def edi_import_orders_handig(self, document):
        data = json.loads(document.content)
        name = self.create_sale_order_handig(data)
        if not name:
            raise except_orm(_('No sales order created!'), _('Something went wrong while creating the sales order.'))
        edi_db = self.env['edi.tools.edi.document.incoming']
	edi_db.message_post(body=_("Sale order <em>%s</em> <b>created</b>.") % (name))
        return True

    @api.model
    def _build_party_header_handig(self, param, data):
	partner_db = self.env['res.partner']
        customer_address = data['billing_address']
        shipping_address = data['shipping_address']
        invoice_address = data['billing_address']

	billing_partner, shipping_partner = self.resolve_customer_info(data['billing_address'], data['shipping_address'], data['email'])

	param['partner_id'] = billing_partner.id
	param['partner_invoice_id'] = billing_partner.id
	param['partner_shipping_id'] = shipping_partner.id.id

        return param

    @api.model
    def create_sale_order_handig(self, data):
	param = {}

        param = self._build_party_header_handig(param, data)
        param = self.create_sale_order(param, data)

        # Actually create the sale order
        
	sid = self.env['sale.order'].create(param)
        so = self.env['sale.order'].browse(sid.id)
	return so.name

    @api.model
    def create_sale_order(self, param, data):
	# Prepare the call to create a sale order
        param['origin'] = data['number']
        param['picking_policy'] = 'one'
        param['client_order_ref'] = data['number']
        #param['fiscal_position'] = 1
	param['pricelist_id'] = 1
	
	# TO DO : Get Fiscal position from partner : self.env['res.partner'].browse(param['partner_id']).property_account_position_id
	#fiscal_pos = self.env['account.fiscal.position'].browse(param['fiscal_position']) or False

        # Create the line items
        pricelist_db = self.env['product.pricelist']
        param['order_line'] = []
        for line in data['line_items']:
	    product = self.env['product.product'].search([('barcode', '=', line['product']['sku'])], limit=1)
            line_params = (0, _, {
                'name' 			: product.name,
                'product_id'            : product.id,
                'product_uom'           : product.uom_id.id,
                'product_uos_qty'       : line['quantity'],
                'product_uom_qty'       : line['quantity'],
                'price_unit'            : line['price'],
                'type'                  : 'make_to_stock',
            })

            param['order_line'].append(line_params)

        return param

    @api.model
    def resolve_customer_info(self, billing_address, shipping_address, email):
        partner_db = self.env['res.partner']
        country_db = self.env['res.country']

        # Check if this partner already exists
        billing_partner = partner_db.search([('email', '=', email)], limit=1)
        if billing_partner:
            # Check if the shipment address exists
            country_id = self.env['res.country'].search([('code', '=', shipping_address['country'])])
            shipping_partner = False
            partners = partner_db.search([('parent_id', '=', billing_partner.id)])
            for partner in partners:
                if self.partner_exists(partner, param, country_id):
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
                'country_id' : country_id[0].id,
                'email'      : email,
                'name'       : billing_address['firstname'] + billing_address['lastname']
            }

            billing_partner = partner_db.create(vals)
            billing_partner = partner_db.browse(billing_partner)

        # If the shipping address doesn't exist yet, create it
        country_id = country_db.search([('code', '=', shipping_address['country'])])
        vals = {
                'active'     : True,
                'customer'   : True,
                'is_company' : False,
                'city'       : shipping_address['city'],
                'zip'        : shipping_address['zipcode'],
                'street'     : shipping_address['street'] + shipping_address['house_number'] + shipping_address['house_number_alt'],
                'country_id' : country_id[0].id,
                'email'      : email,
                'name'       : shipping_address['firstname'] + shipping_address['lastname']
        }

        shipping_partner = partner_db.create(vals)
        shipping_partner = partner_db.browse(shipping_partner)
        return billing_partner, shipping_partner

    @api.model
    def partner_exists(self, partner, params, country_id):
        return partner.name == shipping_address['full_name'] and \
               partner.city == shipping_address['city'] and \
               partner.zip == shipping_address['zipcode'] and \
               partner.street == shipping_address['address1'] and \
               partner.street2 == shipping_address['address2'] and \
               partner.country_id.id == country_id.id
