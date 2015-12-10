import datetime
import logging
import json

from openerp import models, fields, api, _
from openerp.exceptions import except_orm
from openerp.addons.edi_tools.models.exceptions import EdiIgnorePartnerError, EdiValidationError

_logger = logging.getLogger(__name__)

class stock_picking(models.Model):
    _inherit = "stock.picking"

    @api.model
    def valid_for_edi_export_vrd(self, record):
        _logger.info("valid for export")
        return True

    @api.multi
    def send_edi_export_vrd(self, partner_id):
        valid_pickings = self.filtered(self.valid_for_edi_export_vrd)
        invalid_pickings = [p for p in self if p not in valid_pickings]
        if invalid_pickings:
            raise except_orm(_('Invalid pickings in selection!'), _('The following pickings are invalid, please remove from selection. %s') % (map(lambda record: record.name, invalid_pickings)))
        for picking in valid_pickings:
            content = picking.edi_export_vrd(picking)
            result = self.env['edi.tools.edi.document.outgoing'].create_from_content(picking.name, content, partner_id.id, 'stock.picking', 'send_edi_export_vrd')
            if not result:
                raise except_orm(_('EDI creation failed!', _('EDI processing failed for the following picking %s') % (picking.name)))
        return True

    @api.model
    def edi_export_vrd(self, delivery):
        content = self._build_delivery_header(delivery)
        _logger.info("header built")
        content['partner_id'] = self._build_delivery_partner(delivery.partner_id)
        content['move_lines'] = []
        for move in delivery.move_lines:
            content['move_lines'].append(self._build_delivery_move(move))
        return [content]

    @api.model
    def _build_delivery_header(self, delivery):
        return {
            '__id': delivery.id,
            'name': delivery.name,
            'state' : delivery.state,
            'date': delivery.date[:10],
            'min_date': delivery.min_date[:10] or True,
            'origin': delivery.origin or True,
            'order_reference': delivery.order_reference, #to be checked
        }

    @api.model
    def _build_delivery_partner(self, partner):
        return {
            'name': partner.name,
            'ref': partner.ref,
            'lang': partner.lang,
            'website': partner.website,
            'email': partner.email,
            'street': partner.street,
            'street2': partner.street,
            'zip': partner.zip,
            'city': partner.city,
            'country_id': partner.country_id.name,
            'vat': partner.vat,
        }

    @api.model
    def _build_delivery_move(self, move):
        sale_order = self.env['sale.order'].search([('name', '=', self.origin)], limit=1)

        customer_product_code = False
        if sale_order:
            for customer_id in self.product_id.customer_ids:
                if customer_id.name.id in [sale_order.partner_id.parent_id.id, sale_order.partner_id.id]:
                    customer_product_code = customer_id.product_code

        return {
            '__id': move.id,
            'product_qty': move.reserved_availability,
            'name': move.name,
            'weight': move.weight,
            'weight_net': move.weight_net,
            'origin': move.origin,
            'customer_product_code': customer_product_code,
            'product_id': {
                'name': move.product_id.name,
                'ean13': move.product_id.ean13,
            },
        }

    @api.model
    def edi_import_vrd_validator(self, document_ids):
        edi_db = self.env['edi.tools.edi.document.incoming']
        document = edi_db.browse(document_ids)
        document.ensure_one()
        data = json.loads(document.content)[0]
        if data['state'] not in ['done', 'altered', 'cancelled']:
            raise EdiValidationError('No valid state found.')

        # Check if we can find the delivery
        delivery = self.search([('name', '=', data['name'])], limit=1)
        if not delivery:
            raise EdiValidationError('Could not find the referenced delivery: {!s}.'.format(content['name']))

        if delivery.state == 'done':
            raise EdiValidationError("Delivery already transfered.")        

        return True

    @api.model
    def receive_edi_import_vrd(self, document_ids):
        document = self.env['edi.tools.edi.document.incoming'].browse(document_ids)
        document.ensure_one()
        return self.edi_import_vrd(document)

    @api.model
    def edi_import_vrd(self, document):
        data = json.loads(document.content)[0]
        delivery = self.search([('name', '=', data['name'].replace('PCK', 'OUT'))])

        _logger.debug("Delivery found %d (%s)", delivery.id, delivery.name)

        if delivery.partner_id in document.flow_id.ignore_partner_ids:
            msg = "Detected that partner %s (%d) is in the ignore parter list for flow %s (%d)" % (delivery.partner_id.name, delivery.partner_id.id, document.flow_id.name, document.flow_id.id)
            raise EdiIgnorePartnerError(msg)

        if data['state'] != 'cancelled':
            if not delivery.pack_operation_ids:
                delivery.do_prepare_partial()

        if data['state'] == 'done':
            delivery.do_transfer() # execute the transfer of the picking

        if data['state'] == 'altered':
            processed_ids = []
            for edi_line in data['move_lines']:
                move_line = delivery.move_lines.filtered(lambda ml: ml.id == int(edi_line['__id']))
                if len(move_line.linked_move_operation_ids) == 0:
                    raise except_orm(_('No pack operation found!'), _('No pack operation was found for __id %s in picking %s (%d)') % (edi_line['__id'], delivery.name, delivery.id))
                if edi_line['state'] == 'cancelled':
                    next
                pack_operation = move_line.linked_move_operation_ids[0].operation_id
                if edi_line['state'] == 'altered':
                    pack_operation.with_context(no_recompute=True).write({'product_qty': edi_line['product_qty']})
                processed_ids.append(pack_operation.id)

            # delete the others pack operations, they will be included in the backorder
            unprocessed_ids = self.env['stock.pack.operation'].search(['&', ('picking_id', '=', delivery.id), '!', ('id', 'in', processed_ids)])
            unprocessed_ids.unlink()
            delivery.do_transfer() # execute the transfer of the picking

        if data['state'] == 'cancelled':
            delivery.action_cancel()

        return True
