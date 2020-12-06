# -*- coding: utf-8 -*-
##############################################################################
# For copyright and license notices, see __openerp__.py file in root directory
##############################################################################
import logging
import datetime
from odoo import models, fields, api, _
from odoo.exceptions import UserError
_log = logging.getLogger(__name__)

class EdifactDocument(models.Model):
    _inherit = 'edifact.document'

    order_id = fields.Many2one(
        comodel_name='sale.order',
        string='Order')

    def get_product_dict(self, line_dict):
        product_obj = self.env['product.product']
        prod = False
        name = ''
        prod_vals = {}
        # pia_name = line_dict.get('C212#1.7140')
        pia_name = line_dict.get('C212.7140')
        _log.warning('LINE8DICT %s', line_dict)
        _log.warning('PIANAME %s', pia_name)
        prod = product_obj.search([('default_code', 'ilike', pia_name)])
        _log.warning('PROD0 %s', prod)
        if not prod:
            name = pia_name
            prod = product_obj.search([('name', 'ilike', pia_name)])
            _log.warning('PROD1 %s', prod)
        if prod:
            prod_vals['product_id'] = prod.id
        else:
            prod_vals['name'] = name
        return prod_vals

    def get_order_line_vals(self, line_dict, order):
        _log.warning('LINE %s', line_dict)
        line_vals = {}
        # pias = line_dict.get('PIA')
        prod_vals = self.get_product_dict(line_dict)
        for key, value in prod_vals.items():
            line_vals[key] = value
        qty = float(line_dict.get('QTY')[0].get('C186.6060'))
        subtotal = float(line_dict.get('PRI')[0].get('C509.5118'))
        # subtotal = float(line_dict.get('MOA')[0].get('C516.5004'))
        line_vals.update({'product_uom_qty': qty,
                          'price_unit': subtotal / qty,
                          'order_id': order.id})
        return line_vals

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
                raise UserError(_('No client with EAN %s found (Order %s)') % (partner_ean, unh.get('0062')))
            return partner, partner_ean

        vals = {}
        unh = data_dict.get('UNH', {})
        date_old_format = unh.get('DTM', [{}])[0].get('C507.2380')
        vals['date_order'] = datetime.datetime.strptime(date_old_format, '%Y%m%d').strftime('%Y-%m-%d')
        _log.warning('DATE ORDER %s', vals['date_order'])
        currencies = _get_currency(vals, unh)
        vals['currency_id'] = currencies.exists() and currencies[0].id or None
        partner_data = _get_partner(vals, unh)
        _log.warning('partner_data %s', partner_data)
        vals.update({
            # 'ean': partner_data[1],
            'client_order_ref': unh.get('0062'),
            'partner_id': partner_data[0] and partner_data[0].id or None})
        user = self.get_user()
        vals['user_id'] = user and user.id or None
        return vals

    def process_order_in_files(self):
        def _create_order_lines(lines, order):
            _log.warning('LINES %s', lines)
            for lin in lines:
                line_vals = self.get_order_line_vals(lin, order)
                line_obj.create(line_vals)

        def _create_order(data_dict, edi_doc):
            order_vals = self.get_order_vals(data_dict)
            order_vals['edi_doc_id'] = edi_doc.id
            order = order_obj.create(order_vals)
            if unh.get('LOC'):
                for loc in unh.get('LOC'):
                    _create_order_lines(loc.get('LIN'), order)
            else:
                _create_order_lines(unh.get('LIN'), order)
            return order

        order_list = []
        order_obj = self.env['sale.order']
        line_obj = self.env['sale.order.line']
        files = self.read_in_files('orders')
        data_dict_list = []
        edi_doc = False
        for ffile in files:
            order_exist = False
            data_dict_list = self.read_from_file(ffile)
            _log.warning("data_dict_list %s", data_dict_list)
            for data_dict in data_dict_list:
                _log.warning("- data_dict %s", data_dict)
                unh = data_dict.get('UNH', {})
                name = unh.get('0062')
                order_exist = order_obj.search(
                    [('client_order_ref', '=', name)])
                if order_exist:
                    self.move_file_to_duplicated(ffile)
                    break
                edi_doc = self.create({
                    'name': name,
                    'ttype': 'order',
                    'import_log': ''})
                order = _create_order(data_dict, edi_doc)
                order_list.append(order)
                edi_doc.import_log = '\n'.join([
                    edi_doc.import_log, 'OK: %s' % unh.get('0062')])
                edi_doc.state = 'imported'
                edi_doc.order_id = order.id
                edi_doc.file_name = ffile
        files = self.read_in_files('orders')
        [self.delete_file(ffile) for ffile in files]
        return edi_doc

    @api.model
    def cron_process_order_files(self):
        return self.process_order_in_files()
