import json
import logging

from openerp import models, fields, api, _
from openerp.exceptions import except_orm
from openerp.addons.edi_tools.models.exceptions import EdiValidationError

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _inherit = "sale.order"

    @api.model
    def valid_for_edi_export_example_saleorder(self, record):
        if record.state != 'draft':
            return False
        return True

    @api.multi
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

        try:
            data = json.loads(document.content)
        except Exception as e:
            raise EdiValidationError('Content is not valid JSON. %s' % (e))

        for line in data.get('lines', []):
            if not line.get('ean13'):
                raise EdiValidationError('EAN13 missing on line')
            product = self.env['product.product'].search([('ean13', '=', line.get('ean13'))], limit=1)
            if not product:
                raise EdiValidationError('There is no product with ean13 number %s' % (line.get('ean13')))

    @api.model
    def receive_edi_import_example_saleorder(self, document_id):
        document = self.env['edi.tools.edi.document.incoming'].browse(document_id)
        return self.edi_import_example_saleorder(document)

    @api.model
    def edi_import_example_saleorder(self, document):
        data = json.loads(document.content)

        params = {
            'partner_id': document.partner_id.id,
            'date_order': data['date'],
            'client_order_ref': data['reference'],
            'order_line': []
        }

        for line in data['lines']:
            product = self.env['product.product'].search([('ean13', '=', line['ean13'])], limit=1)

            line_params = {
                'product_uos_qty' : line['quantity'],
                'product_uom_qty' : line['quantity'],
                'product_id'      : product.id,
                'price_unit'      : product.list_price,
                'name'            : product.name,
                'tax_id'          : [[6, False, self.env['account.fiscal.position'].map_tax(product.taxes_id).ids]],
            }

            params['order_line'].append([0, False, line_params])

        return self.env['sale.order'].create(params)
