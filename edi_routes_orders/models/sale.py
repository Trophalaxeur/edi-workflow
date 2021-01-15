import datetime
import json
import pytz
import csv
import logging

from io import StringIO
from odoo.exceptions import except_orm
from odoo.addons.edi_tools.models.edi_mixing import EDIMixin
from odoo.addons.edi_tools.models.exceptions import EdiValidationError
from odoo import api, _, models

_logger = logging.getLogger(__name__)

def is_dst():
    _logger.debug("Calcuating TZ")
    tz = pytz.timezone("Europe/Brussels")
    now = pytz.utc.localize(datetime.datetime.utcnow())
    return now.astimezone(tz).dst() != datetime.timedelta(0)

class sale_order(models.Model, EDIMixin):
    _name = "sale.order"
    _inherit = "sale.order"

    def edi_import_orders_d96a_validator(self, document_id):
        _logger.info('StartValidatingD96A!!')
        document = self.env['edi.tools.edi.document.incoming'].browse(document_id)

        _logger.warning('edi_import_orders_d96a_validator')
        try:
            _logger.warning('TRY JSON 2')
            datas = json.loads(document.content)
        except Exception as e:
            _logger.warning('JSON FAIL %s', e)
            pass
        try:
            dummy_file = StringIO(document.content)
            datas = csv.reader(dummy_file, delimiter=',', quotechar='"')
        except Exception as e:
            _logger.warning('CSV FAIL %s', e)
            raise EdiValidationError('Content is not valid CSV nor JSON. %s' % (e))

        # Does this document have the correct root name?
        if not 'message' in data:
            raise EdiValidationError('Could not find field: message.')
        data = data['message']

        # Validate the document reference
        if not 'docnum' in data:
            raise EdiValidationError('Could not find field: docnum.')

        order_ids = self.search([('client_order_ref', '=', data['docnum']), ('state', '!=', 'cancelled')])
        if order_ids:
            order = self.browse(order_ids)[0]
            raise EdiValidationError("Sales order %s exists for this reference" % (order.name,))

        # Validate the sender
        if not 'sender' in data:
            raise EdiValidationError('Could not find field: sender.')

        # Validate all the partners
        found_by = False
        found_dp = False
        found_iv = False
        if not 'partys' in data:
            raise EdiValidationError('Could not find field: partys.')
        try:
            data['partys'] = data['partys'][0]['party']
        except Exception:
            raise EdiValidationError('Erroneous structure for table: partys.')
        if len(data['partys']) == 0:
            raise EdiValidationError('Content of table partys is empty. ')

        partner_db = self.pool.get('res.partner')
        for party in data['partys']:
            if not 'qual' in party:
                raise EdiValidationError('Could not find field: qual (partner).')
            if not 'gln' in party:
                raise EdiValidationError('Could not find field: gln (partner).')
            pids = partner_db.search([('ref', '=', party['gln'])])
            if not pids:
                raise EdiValidationError('Could not resolve partner {!s}.'.format(party['gln']))
            if party['qual'] == 'BY':
                found_by = True
            elif party['qual'] == 'DP':
                found_dp = True
        if not found_by or not found_dp:
            raise EdiValidationError('Couldnt find all required partners BY,DP.')

        # Validate all the line items
        if not 'lines' in data:
            raise EdiValidationError('Could not find field: lines.')
        try:
            data['lines'] = data['lines'][0]['line']
        except Exception:
            raise EdiValidationError('Erroneous structure for table: lines.')
        if len(data['lines']) == 0:
            raise EdiValidationError('Content of table lines is empty. ')

        product = self.pool.get('product.product')
        for line in data['lines']:
            if not 'ordqua' in line:
                raise EdiValidationError('Could not find field: ordqua (line).')
            if line['ordqua'] < 1:
                raise EdiValidationError('Ordqua (line) should be larger than 0.')
            if not 'gtin' in line:
                raise EdiValidationError('Could not find field: gtin (line).')
            pids = product.search([('ean13', '=', line['gtin'])])
            if not pids:
                raise EdiValidationError('Could not resolve product {!s}.'.format(line['gtin']))

        # Validate timing information
        #if not 'deldtm' in data:
        #    raise EdiValidationError('Could not find field: deldtm.')
        #if not 'latedeltm' in data:
        #    raise EdiValidationError('Could not find field: latedeltm.')
        #if (not 'deldtm' in data) and (not 'latedeldtm' in data):
        #    raise EdiValidationError('Could not find field: deldtm or latedeldtm.')
        if not 'docdtm' in data:
            raise EdiValidationError('Could not find field: docdtm.')

        # If we get all the way to here, the document is valid
        _logger.info('validatedD96A!!')
        return True

    def receive_edi_import_orders_d93a(self, ids, context=None):
        edi_db = self.pool.get('edi.tools.edi.document.incoming')
        document = edi_db.browse(ids, context)
        return self.edi_import_orders_d93a(document, context=context)

    def edi_import_orders_d93a(self, document, context=None):
        data = json.loads(document.content)
        data = data['message']
        data['partys'] = data['partys'][0]['party']
        data['lines'] = data['lines'][0]['line']
        name = self.create_sale_order_d93a(data, context)
        if not name:
            raise except_orm(_('No sales order created!'), _('Something went wrong while creating the sales order.'))
        edi_db = self.pool.get('edi.tools.edi.document.incoming')
        edi_db.message_post(document.id, body='Sale order {!s} created'.format(name))
        return True

    def receive_edi_import_orders_d96a(self, ids, context=None):
        edi_db = self.pool.get('edi.tools.edi.document.incoming')
        document = edi_db.browse(ids, context)
        return self.edi_import_orders_d96a(document, context=context)

    def edi_import_orders_d96a(self, document, context=None):
        _logger.info('importingD96A!!')
        data = json.loads(document.content)
        data = data['message']
        data['partys'] = data['partys'][0]['party']
        data['lines'] = data['lines'][0]['line']
        name = self.create_sale_order_d96a(data, context)
        if not name:
            raise except_orm(_('No sales order created!'), _('Something went wrong while creating the sales order.'))
        edi_db = self.pool.get('edi.tools.edi.document.incoming')
        edi_db.message_post(document.id, body='Sale order {!s} created'.format(name))
        return True

    def _build_party_header_93a(self, param, data, context=None):
        _logger.info('prepartyD96A!!')
        partner_db = self.pool.get('res.partner')
        for party in data['partys']:
            if party['qual'] == 'BY':
                pids = partner_db.search([('ref', '=', party['gln'])])
                buyer = partner_db.browse(pids, context)[0]
                param['partner_id'] = buyer.id
                param['user_id'] = buyer.user_id.id
                param['fiscal_position'] = buyer.property_account_position.id
                param['payment_term'] = buyer.property_payment_term.id
                param['pricelist_id'] = buyer.property_product_pricelist.id
                fiscal_pos = self.pool.get('account.fiscal.position').browse(buyer.property_account_position.id) or False

            if party['qual'] == 'PR':
                pids = partner_db.search([('ref', '=', party['gln'])])
                iv = partner_db.browse(pids, context)[0]
                param['partner_invoice_id'] = iv.id

            if party['qual'] == 'DP':
                pids = partner_db.search([('ref', '=', party['gln'])])
                dp = partner_db.browse(pids, context)[0]
                param['partner_shipping_id'] = dp.id

        # if IV partner is not present invoice partner is
        #  - parent of BY or
        #  - BY

        if not param.get('partner_invoice_id', None):
            buyer = partner_db.browse(param['partner_id'], context)
            param['partner_invoice_id'] = buyer.id
            if buyer.parent_id:
                param['partner_invoice_id'] = buyer.parent_id.id

        if 'partner_shipping_id' not in param:
            param['partner_shipping_id'] = param['partner_id']
        
        _logger.info('postpartnerD96A!!')

        return param

    def _build_party_header_96a(self, param, data, context=None):
        partner_db = self.pool.get('res.partner')
        for party in data['partys']:
            if party['qual'] == 'BY':
                pids = partner_db.search([('ref', '=', party['gln'])])
                buyer = partner_db.browse(pids, context)[0]
                param['partner_id'] = buyer.id
                param['user_id'] = buyer.user_id.id
                param['fiscal_position'] = buyer.property_account_position.id
                param['payment_term'] = buyer.property_payment_term.id
                param['pricelist_id'] = buyer.property_product_pricelist.id
                fiscal_pos = self.pool.get('account.fiscal.position').browse(buyer.property_account_position.id) or False

            if party['qual'] == 'IV':
                pids = partner_db.search([('ref', '=', party['gln'])])
                iv = partner_db.browse(pids, context)[0]
                param['partner_invoice_id'] = iv.id

            if party['qual'] == 'DP':
                pids = partner_db.search([('ref', '=', party['gln'])])
                dp = partner_db.browse(pids, context)[0]
                param['partner_shipping_id'] = dp.id

        # if IV partner is not present invoice partner is
        #  - parent of BY or
        #  - BY

        if not param.get('partner_invoice_id', None):
            buyer = partner_db.browse(param['partner_id'], context)
            param['partner_invoice_id'] = buyer.id
            if buyer.parent_id:
                param['partner_invoice_id'] = buyer.parent_id.id

        if 'partner_shipping_id' not in param:
            param['partner_shipping_id'] = param['partner_id']

        return param

    def create_sale_order_d93a(self, data, context=None):
        param = {}

        param = self._build_party_header_93a(param, data, context)
        param = self.create_sale_order(param, data, context)

        # Actually create the sale order
        sid = self.create(param, context=None)
        so = self.browse([sid], context)[0]
        return so.name

    def create_sale_order_d96a(self, data, context=None):
        _logger.info('preppingD96A!!')
        param = {}

        param = self._build_party_header_96a(param, data, context)
        param = self.create_sale_order(param, data, context)

        # Actually create the sale order
        sid = self.create(param, context=None)
        so = self.browse([sid], context)[0]
        return so.name

    def create_sale_order(self, param, data, context):
        # Prepare the call to create a sale order
        _logger.info('prepping!!')
        param['origin'] = data['docnum']
        param['picking_policy'] = 'direct'
        #if crossdock order:
        if data['docsrt'] == "50E":
           param['instruction_2'] = 'XDCK'
        #if launch order:
        if data['docsrt'] == "221":
            param['instruction_2'] = 'RMORD'
        _logger.info('gogogo')
        if 'ordertype' in data:
            _logger.info('ordertype detected')
            #if Intake / Shop / Install
            if data['ordertype'] == '77E':
                param['instruction_2'] = param['instruction_2'] + ' 77E'
            #if Comission
            if data['ordertype'] == '83E':
                param['instruction_2'] = param['instruction_2'] + ' 83E'
                param['picking_policy'] = 'one'
        #if Campaign
        #if 'orderrefpd' in data:
        #    param['origin'] = param['origin'] + ' CAMP' + data['orderrefpd']
        param['message_follower_ids'] = False
        param['categ_ids'] = False
        #param['picking_policy'] = 'one'
        param['order_policy'] = 'picking'
        param['carrier_id'] = False
        param['invoice_quantity'] = 'order'
        _logger.info('setting client_order_ref')
        param['client_order_ref'] = data['docnum']
        
        if 'orderrefct' in data:
            param['instruction_1'] = 'CC ' + data['orderrefct']
        if 'orderrefpd' in data:
            param['instruction_1'] = 'OPECO ' + data['orderrefpd']
        if 'orderrefcr' in data:
            param['instruction_2'] = param['instruction_2'] + ' CR ' +data['orderrefcr']
        
        _logger.info('no instruction 1 or 2 found')
        requested_date_key = 'deldtm'
        if 'deldtm' not in data:
            requested_date_key = 'latedeldtm'
        param['requested_date'] = data[requested_date_key][:4] + '-' + data[requested_date_key][4:6] + '-' + data[requested_date_key][6:8]
        if is_dst():
            _logger.debug("Delivery calculated in DST")
            #if param['partner_shipping_id'] == 526:
            #    param['requested_date'] = param['requested_date'] + ' 04:30:00'
            #if param['partner_shipping_id'] == 560:
            #    param['requested_date'] = param['requested_date'] + ' 8:30:00'
            #if param['partner_shipping_id'] == 562:
            #    param['requested_date'] = param['requested_date'] + ' 07:30:00'
            #if param['partner_shipping_id'] == 561:
            #    param['requested_date'] = param['requested_date'] + ' 08:30:00'
            #if param['partner_shipping_id'] == 570:
            #    param['requested_date'] = param['requested_date'] + ' 10:00:00'
            param['requested_date'] = param['requested_date'] + ' 08:30:00'
        else:
            #_logger.debug("Delivery calculated without DST")
            #if param['partner_shipping_id'] == 526:
            #    param['requested_date'] = param['requested_date'] + ' 05:30:00'
            #if param['partner_shipping_id'] == 560:
            #    param['requested_date'] = param['requested_date'] + ' 9:30:00'
            #if param['partner_shipping_id'] == 562:
            #    param['requested_date'] = param['requested_date'] + ' 08:30:00'
            #if param['partner_shipping_id'] == 561:
            #    param['requested_date'] = param['requested_date'] + ' 09:30:00'
            #if param['partner_shipping_id'] == 570:
            #    param['requested_date'] = param['requested_date'] + ' 11:00:00'
            param['requested_date'] = param['requested_date'] + ' 08:30:00'
        param['message_ids'] = False
        param['note'] = False
        param['project_id'] = False
        param['incoterm'] = False
        param['section_id'] = False
        fiscal_pos = self.pool.get('account.fiscal.position').browse(param['fiscal_position']) or False
        if 'user_id' not in param:
            param['user_id'] = uid
        elif not param['user_id']:
            param['user_id'] = uid

        _logger.debug("Finished Building Header")

        # Create the line items
        product_db = self.pool.get('product.product')
        pricelist_db = self.pool.get('product.pricelist')
        param['order_line'] = []

        _logger.debug("Start Processing Order Lines")
        for line in data['lines']:

            pids = product_db.search([('ean13', '=', line['gtin'])])
            prod = product_db.browse(pids, context)[0]

            detail = {}
            detail['property_ids'] = False
            detail['product_uos_qty'] = line['ordqua']
            detail['product_id'] = prod.id
            detail['product_uom'] = prod.uom_id.id

            # If the price is given from the file, use that
            # Otherwise, use the price from the pricelist
            _logger.debug("Looking for prices")
            if 'price' in line:
                detail['price_unit'] = line['price']
            else:
                detail['price_unit'] = pricelist_db.price_get([param['pricelist_id']], prod.id, 1, 2640)[param['pricelist_id']]

            detail['product_uom_qty'] = line['ordqua']
            detail['customer_product_code'] = False
            # If a description is given from the customer, use that as the product name.
            _logger.debug("Looking for description for product %s", prod.id)
            if 'desc' in line:
                _logger.debug("Description Given")
                detail['name'] = line['desc'] + ' ' + prod.name
            else:
                _logger.debug("Description from MD")
                #detail['name'] = prod.name + ' ' + prod.description_sale
                detail['name'] = prod.name + ' ' + prod.description
            _logger.debug("Description set")
            detail['delay'] = False
            detail['discount'] = False
            detail['address_allotment_id'] = False
            _logger.debug("Calc Weight")
            if prod.weight > 0:
                detail['th_weight'] = prod.weight * float(line['ordqua'])
            else:
                detail['th_weight'] = (prod.weight+0.01) * float(line['ordqua'])
            detail['product_uos'] = False
            detail['type'] = 'make_to_stock'
            detail['product_packaging'] = False

            # Tax swapping calculations u'tax_id': [[6,False, [1,3] ]],
            detail['tax_id'] = False
            _logger.debug("Calc Taxes")
            if prod.taxes_id:
                detail['tax_id'] = [[6, False, []]]
                if fiscal_pos:
                    new_taxes = self.pool.get('account.fiscal.position').map_tax(fiscal_pos, prod.taxes_id)
                    if new_taxes:
                        detail['tax_id'][0][2] = new_taxes
                    else:
                        for tax in prod.taxes_id:
                            detail['tax_id'][0][2].append(tax.id)
                else:
                    for tax in prod.taxes_id:
                        detail['tax_id'][0][2].append(tax.id)

            order_line = []
            order_line.extend([0])
            order_line.extend([False])
            order_line.append(detail)
            param['order_line'].append(order_line)
            _logger.debug("Line Added !")

        return param

    def _get_date_planned(self, order, line, start_date, context=None):
        result = super(sale_order, self)._get_date_planned(order, line, start_date, context)
        if order.requested_date:
            result = order.requested_date
        return result
