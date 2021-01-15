import json
import csv
import logging
import datetime

from io import StringIO
from odoo import models, api, _
from odoo.exceptions import except_orm
from odoo.addons.edi_tools.models.exceptions import EdiValidationError

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _inherit = "sale.order"

    @api.model
    def valid_for_edi_export_example_saleorder(self, record):
        if record.state != 'draft':
            return False
        return True

    
    def send_edi_export_example_saleorder(self, partner_id):
        valid_orders = self.filtered(self.valid_for_edi_export_example_saleorder)
        invalid_orders = [p for p in self if p not in valid_orders]
        if invalid_orders:
            raise except_orm(_('Invalid sale orders in selection!'), _('The following sale orders are invalid, please remove from selection. %s') % (map(lambda record: record.name, invalid_orders)))
        for order in self:
            content = order.edi_export_example_saleorder(order)
            result = self.env['edi.tools.edi.document.outgoing'].create_from_content(order.name, content, partner_id.id, 'sale.order', 'send_edi_export_example_saleorder')
            if not result:
                raise except_orm(_('EDI creation failed!', _('EDI processing failed for the following order %s') % (order.name)))
        return True

    @api.model
    def edi_export_example_saleorder(self, order):
        return self.env['sale.order'].edi_export(order)

    @api.model
    def edi_import_example_saleorder_validator(self, document_id):
        document = self.env['edi.tools.edi.document.incoming'].browse(document_id)

        _logger.warning('edi_import_example_saleorder_validator')
        try:
            _logger.warning('TRY JSON 1')
            datas = json.loads(document.content)
        except Exception as e:
            _logger.warning('JSON FAIL %s', e)
            pass
        try:
            _logger.warning('TRY CSV')
            dummy_file = StringIO(document.content)
            datas = csv.reader(dummy_file, delimiter=',', quotechar='"')
        except Exception as e:
            _logger.warning('CSV FAIL %s', e)
            raise EdiValidationError('Content is not valid CSV nor JSON. %s' % (e))

        # try:
        #     datas = json.loads(document.content)
        # except Exception as e:
        #     pass

        #     raise EdiValidationError('Content is not valid JSON. %s' % (e))

        # for line in datas.get('lines', []):
        #     if not line.get('ean13'):
        #         raise EdiValidationError('EAN13 missing on line')
        #     product = self.env['product.product'].search([('barcode', '=', line.get('ean13'))], limit=1)
        #     if not product:
        #         raise EdiValidationError('There is no product with ean13/barcode number %s' % (line.get('ean13')))
        return True

    @api.model
    def receive_edi_import_example_saleorder(self, document_id):
        document = self.env['edi.tools.edi.document.incoming'].browse(document_id)
        return self.edi_import_example_saleorder(document)

    @api.model
    def edi_import_example_saleorder(self, document):
        _logger.warning('IN edi_import_example_saleorder')
        filetype = document.name.split('.')[-1]
        _logger.warning('filetype %s', filetype)
        _logger.warning('location %s', document.location + '/' + document.name)
        _logger.warning('edifact.document %s', self.env['edifact.document'])

        if filetype != 'edi':
            _logger.error('Only EDI files are supported for now')
            raise EdiValidationError('Document is not an edi file.')

        # dummy_file = StringIO(document.content)
        # data = csv.reader(dummy_file, delimiter=';', quotechar='"')
        datas = self.env['edifact.document'].read_from_file(document.location + '/' + document.name)
        _logger.warning('DATAS %s', datas)
        return self.create_SO_from_data(datas)


        # params = {
        #     'partner_id': document.partner_id.id,
        #     'date_order': data['date'],
        #     'client_order_ref': data['reference'],
        #     'order_line': []
        # }

        # for line in data['lines']:

        #     product = self.env['product.product'].search([('barcode', '=', line['ean13'])], limit=1)

        #     line_params = {
        #         'product_uom_qty' : line['quantity'],
        #         'product_id'      : product.id,
        #         'price_unit'      : product.list_price,
        #         'name'            : product.name,
        #         'tax_id'          : [[6, False, self.env['account.fiscal.position'].map_tax(product.taxes_id).ids]],
        #     }

        #     params['order_line'].append([0, False, line_params])

        # return self.env['sale.order'].create(params)


    def create_SO_from_data(self, datas):
        for data in datas:
            _logger.warning("- data_dict %s", data)
            unh = data.get('UNH', {})
            name = unh.get('0062')
            order_exist = self.env['sale.order'].search([('client_order_ref', '=', name)])
            if order_exist:
                # self.move_file_to_duplicated(ffile)
                _logger.error('DUPLICATED ! A GERER')
                raise EdiValidationError('Duplicated !')
                break

            order = self._create_order(data, unh)
            # order_list.append(order)
            # edi_doc.import_log = '\n'.join([
            #     edi_doc.import_log, 'OK: %s' % unh.get('0062')])
            # edi_doc.state = 'imported'
            # edi_doc.order_id = order.id
            # edi_doc.file_name = ffile
        return True

    def _create_order_lines(self, lines, order, order_params):
        _logger.warning('LINES %s', lines)
        for lin in lines:
            line_vals = self.get_order_line_vals(lin, order)
            order_params['order_line'].append([0, False, line_vals])
            # self.env['sale.order.line'].create(line_vals)

    def _create_order(self, data_dict, unh):
        order_vals = self.get_order_vals(data_dict)

        _logger.warning('ORDER_VALS BEFORE%s', order_vals)
        # line_params = {}
        if unh.get('LOC'):
            for loc in unh.get('LOC'):
                self._create_order_lines(loc.get('LIN'), False, order_vals)
                # order_vals['order_line'].append([0, False, line_params])
        else:
            self._create_order_lines(unh.get('LIN'), False, order_vals)
            # order_vals['order_line'].append([0, False, line_params])
        _logger.warning('ORDER_VALS %s', order_vals)
        order = self.env['sale.order'].create(order_vals)

        return order

    def get_order_vals(self, data_dict):
        def _get_currency(vals, unh):
            return self.env['res.currency'].search(
                [('name', '=', unh.get('CUX', [{}])[0].get('C504#1.6345'))])

        def _get_partner(vals, unh):
            name_and_address = unh.get('NAD', [{}])
            buyer_purchase_order = 'BY'
            partner_ean = [
                n['C082.3039'] for n in name_and_address
                if '3035' in n and n['3035'] == buyer_purchase_order]
            partner_ean = partner_ean and str(partner_ean[0]) or []
            partner = self.env['res.partner'].search(
                [('barcode', 'ilike', partner_ean)])
            if not partner:
                raise EdiValidationError(_('No client with EAN %s found (Order %s)') % (partner_ean, unh.get('0062')))
            return partner, partner_ean

        vals = {'order_line': []}
        unh = data_dict.get('UNH', {})
        date_old_format = unh.get('DTM', [{}])[0].get('C507.2380')
        vals['date_order'] = datetime.datetime.strptime(date_old_format, '%Y%m%d').strftime('%Y-%m-%d')
        _logger.warning('DATE ORDER %s', vals['date_order'])
        currencies = _get_currency(vals, unh)
        vals['currency_id'] = currencies.exists() and currencies[0].id or None
        partner_data = _get_partner(vals, unh)
        _logger.warning('partner_data %s', partner_data)
        vals.update({
            # 'ean': partner_data[1],
            'client_order_ref': unh.get('0062'),
            'partner_id': partner_data[0] and partner_data[0].id or None})
        user = self.get_user()
        vals['user_id'] = user and user.id or None
        return vals

    def get_order_line_vals(self, line_dict, order):
        _logger.warning('LINE %s', line_dict)
        line_vals = {}
        # pias = line_dict.get('PIA')
        prod_vals = self.get_product_dict(line_dict)
        for key, value in prod_vals.items():
            line_vals[key] = value
        qty = float(line_dict.get('QTY')[0].get('C186.6060'))
        subtotal = float(line_dict.get('PRI')[0].get('C509.5118'))
        # subtotal = float(line_dict.get('MOA')[0].get('C516.5004'))
        # line_vals.update({'product_uom_qty': qty,
        #                   'price_unit': subtotal / qty,
        #                   'order_id': order.id})
        line_vals.update({'product_uom_qty': qty,
                          'price_unit': subtotal / qty})
        _logger.warning('LINE_VALS %s', line_vals)
        return line_vals

    def get_product_dict(self, line_dict):
        product_obj = self.env['product.product']
        # product_tpl_obj = self.env['product.template']
        prod = False
        name = ''
        prod_vals = {}
        # pia_name = line_dict.get('C212#1.7140')
        pia_name = line_dict.get('C212.7140')
        _logger.warning('LINE8DICT %s', line_dict)
        _logger.warning('PIANAME %s', pia_name)
        prod = product_obj.search([('barcode', 'ilike', pia_name)])
        _logger.warning('PROD0 %s', prod)
        if not prod:
            prod = product_obj.search([('default_code', 'ilike', pia_name)])
            _logger.warning('PROD1 %s', prod)
        if not prod:
            prod = product_obj.search([('name', 'ilike', pia_name)])
            _logger.warning('PROD2 %s', prod)
        if prod:
            prod_vals['product_id'] = prod.id
        else:
            # prod_vals['name'] = name
            raise EdiValidationError(_('No product with EAN %s found') % (pia_name))
        return prod_vals

    def get_user(self):
        company = self.env['res.company'].browse(self.env.company.id)
        return company and company.user_id or None