import base64
import time, datetime
import csv, StringIO
from itertools import groupby

from openerp.osv import fields, osv
from openerp.tools.translate import _
from openerp import tools

import logging

_logger = logging.getLogger(__name__)

class essers_pclo_import(osv.osv_memory):
    _name = 'essers.pclo.import'
    _description = 'Import Essers PCLO File'
    _columns = {
        'pclo_data': fields.binary('PCLO File', required=True),
        'pclo_fname': fields.char('PCLO Filename', size=128, required=True),
        'note': fields.text('Log'),
    }

    _defaults = {
        'pclo_fname': 'pclo.csv',
    }

    def pclo_parsing(self, cr, uid, ids, context=None, batch=False, pclofile=None, pclofilename=None):
        if context is None:
            context = {}

        data = self.browse(cr, uid, ids)[0]
        try:
            pclofile = unicode(base64.decodestring(data.pclo_data))
            pclofilename = data.pclo_fname
        except:
            raise osv.except_osv(_('Error'), _('Wizard in incorrect state. Please hit the Cancel button'))
            return {}

        pick_out_db = self.pool.get('stock.picking')
        content = pclofile.split("\n")
        if pick_out_db.edi_import_essers_pclo(cr, uid, content, context=context):
            return {'type': 'ir.actions.act_window_close'}
        else:
            return {}
