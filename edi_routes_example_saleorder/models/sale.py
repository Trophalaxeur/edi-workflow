import json
import csv
import logging

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
            _logger.warning('TRY JSON')
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
        _logger.warning('edi_import_example_saleorder')
        filetype = document.name.split('.')[-1]
        if filetype == 'json':
            _logger.warning('JSON DATAS')
            data = json.loads(document.content)
        elif filetype == 'csv':
            _logger.warning('CSV DATAS')
            dummy_file = StringIO(document.content)
            data = csv.reader(dummy_file, delimiter=';', quotechar='"')
            _logger.warning('DATA %s', data)
            for row in data:
                _logger.warning(row)

        params = {
            'partner_id': document.partner_id.id,
            'date_order': data['date'],
            'client_order_ref': data['reference'],
            'order_line': []
        }

        for line in data['lines']:

            product = self.env['product.product'].search([('barcode', '=', line['ean13'])], limit=1)

            line_params = {
                'product_uom_qty' : line['quantity'],
                'product_id'      : product.id,
                'price_unit'      : product.list_price,
                'name'            : product.name,
                'tax_id'          : [[6, False, self.env['account.fiscal.position'].map_tax(product.taxes_id).ids]],
            }

            params['order_line'].append([0, False, line_params])

        return self.env['sale.order'].create(params)
