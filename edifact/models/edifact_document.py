# -*- coding: utf-8 -*-
##############################################################################
# For copyright and license notices, see __openerp__.py file in root directory
##############################################################################
from odoo import models, fields, api, exceptions, _
import logging
_log = logging.getLogger(__name__)
try:
    from odoo.addons.edifact.botsapi import inmessage
except ImportError:
    _log.warning('Error while importing bots libraries 1')
try:
    from odoo.addons.edifact.botsapi import outmessage, botsinit, botsglobal
    from odoo.addons.edifact.botsapi.outmessage import json as json_class
except ImportError:
    _log.warning('Error while importing bots libraries 2')
try:
    from os import listdir, remove, rename
    from os.path import isfile, join, exists
    import atexit
except ImportError:
    _log.warning('Error while importing libraries')


class EdifactDocument(models.Model):
    _name = 'edifact.document'
    _descripction = 'Edifact Document'
    _inherit = ['mail.thread']
    _order = 'id desc'

    name = fields.Char(
        string='Reference',
        required=True,
        track_visibility='onchange')
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        default=(lambda self: self.env['res.company']._company_default_get(
            'edifact.document')))
    ttype = fields.Selection(
        selection=[
            ('order', 'Sale Order'),
            ('picking', 'Stock Picking'),
            ('invoice', 'Out Invoice'),
            ('voucher', 'Customer Voucher')
        ],
        string='Document Type',
        track_visibility='onchange')
    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('imported', 'Imported'),
            ('exported', 'Exported'),
            ('error', 'Error'),
        ],
        string='State',
        required=True,
        default='draft')
    date = fields.Datetime(
        string='Creation Date',
        required=True,
        default=fields.Datetime.now(),
        track_visibility='onchange')
    import_log = fields.Text(
        string='Import Log',
        translate=True)
    file_name = fields.Char(
        string='File Name')

    def limit_string(self, string, num_char):
        return string and string[:num_char] or ''

    def get_order_number(self, origin):
        order = self.env['sale.order'].search([(
            'name', '=', origin)])
        return order and self.limit_string(order[0].client_order_ref, 35) or (
            self.limit_string(origin, 35))

    def get_picking(self, origin):
        if not origin:
            return ''
        order = self.env['sale.order'].search([(
            'name', '=', origin)])
        if not order:
            return origin
        return order.picking_ids and self.limit_string(
            order.picking_ids[0].name, 35) or (self.limit_string(origin, 35))

    def ls_files(self, path, ttype=None):
        if ttype:
            path = '/'.join([path, ttype])
        if exists(path):
            return ['/'.join([path, arch])
                    for arch in listdir(path) if isfile(join(path, arch))]
        return []

    def get_path(self, ttype):
        company = self.env['res.company'].browse(self.env.company.id)
        if not company:
            return False
        if ttype == 'in':
            return company.in_path
        if ttype == 'out':
            return company.out_path
        if ttype == 'duplicated':
            return company.duplicated_path

    def get_user(self):
        company = self.env['res.company'].browse(self.env.company.id)
        return company and company.user_id or None

    def delete_file(self, path):
        remove(path)

    def move_file_to_duplicated(self, path):
        path_split = path.split('/')
        file_name = path_split[len(path_split) and len(path_split) - 1 or '']
        rename(path, '/'.join([self.get_path('duplicated'), file_name]))

    def read_in_files(self, ttype=None):
        path = self.get_path('in')
        return self.ls_files(path, ttype)

    def write_in_file(self, ttype, file_name, file_content):
        path = self.get_path('in')
        f = open('/'.join([path, ttype, file_name]), 'w+b')
        f.write(file_content)
        f.close()
        return '/'.join([path, ttype, file_name])

    def write_out_file(self, ttype, file_name, file_content):
        path = self.get_path('out')
        f = open('/'.join([path, ttype, file_name]), 'w+')
        f.write(file_content)
        f.close()
        return '/'.join([path, ttype, file_name])

    def read_from_file(self, path):
        configdir = '/mnt/extra-addons/edifact/botsapi/config'
        botsinit.generalinit(configdir)
        # process_name = 'odoo_get_edi'
        # botsglobal.logger = botsinit.initenginelogging(process_name)
        atexit.register(logging.shutdown)
        ta_info = {
            'alt': '',
            'charset': '',
            'command': 'new',
            'editype': 'edifact',
            'filename': path,
            'fromchannel': '',
            'frompartner': '',
            'idroute': '',
            'messagetype': 'edifact',
            'testindicator': '',
            'topartner': ''}
        try:
            edifile = inmessage.parse_edi_file(**ta_info)
            _log.warning("EDIFILE %s", edifile)
            if edifile.errorfatal:
                _log.warning("EDIFILE error list %s", edifile.errorlist)
                for errmsg in edifile.errorlist:
                    _log.warning("error %s", errmsg)

                raise exceptions.Warning(_('Error, TOTO Details:'))
        except Exception as e:
            if '[A59]' in str(e):
                raise exceptions.Warning(
                    _('Edi file has codification errors.'),
                    _('Check accents and other characters not allowed '
                      'in the edi document'))
            raise exceptions.Warning(_(
                'It has occurred following error: %s.' % e))
        json_ins = outmessage.json(edifile.ta_info)
        struc = [{ms.root.record['BOTSID']:
                 json_class._node2json(json_ins, ms.root)}
                 for ms in edifile.nextmessage()]
        _log.warning("STRUC %s", struc)
        return struc
