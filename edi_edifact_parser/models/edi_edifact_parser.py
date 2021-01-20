# -*- coding: utf-8 -*-
##############################################################################
# For copyright and license notices, see __manifest__.py file in root directory
##############################################################################
from odoo import models, fields, api, exceptions, _
import logging
_log = logging.getLogger(__name__)

try:
    from odoo.addons.edifact.botsapi import inmessage, outmessage, botsinit, botsglobal
    from odoo.addons.edifact.botsapi.outmessage import json as json_class
except ImportError:
    _log.warning('Error while importing bots libraries')
try:
    from os import listdir, remove, rename
    from os.path import isfile, join, exists
    import atexit
except ImportError:
    _log.warning('Error while importing libraries')


class EdiEdifactParser(models.Model):
    _name = 'edi.edifact.parser'
    _description = 'EDI Edifact Document'

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
        return struc
