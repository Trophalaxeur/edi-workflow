import datetime
import logging

from odoo import api, fields, models, _
from odoo.addons import decimal_precision as dp
from odoo.exceptions import except_orm
from odoo.tools import float_utils

from odoo.addons.edi_tools.models.edi_mixing import EDIMixin
from odoo.addons.edi_tools.models.exceptions import EdiIgnorePartnerError, EdiValidationError

_logger = logging.getLogger(__name__)

class InventoryLine(models.Model):
    _inherit = "stock.inventory.line"
    
class Inventory(models.Model, EDIMixin):
    _inherit = "stock.inventory"
    
    #Import section
    @api.model
    def edi_import_calwms_inventory_validator(self, document_ids):
        _logger.info("Validating CALwms document")
        return True

    @api.model
    def receive_edi_import_calwms_inventory(self, document_ids):
        document = self.env['edi.tools.edi.document.incoming'].browse(document_ids)
        document.ensure_one()
        return self.edi_import_calwms_inventory(document)

    @api.model
    def edi_import_calwms_inventory(self, document):
        content = document.content
        name = self.create_stock_inventory(content)
        if not name:
            raise except_orm(_('No Inventory created!'), _('Something went wrong while creating the stock inventory.'))
        
        edi_db = self.pool.get('edi.tools.edi.document.incoming')
        edi_db.message_post(cr, uid, document.id, body='Inventory {!s} created'.format(name))

        return True

    @api.model
    def create_stock_inventory(self, content):
        _logger.info('prepping inventory!')
        param = {}
        param = self.create_inventory(param, content)

        # Actually create the inventory file
        so = self.browse([sid])[0]
        return so.name

    def create_inventory(self, param, content):
        # Prepare the call to create an Inventory
        _logger.info('prepping!!')
        param['name'] = 'Testje'
        iid = self.create(param)
        iid.action_start()
        Product = self.env['product.product']
        for sl in iid.line_ids: 
        #delivery = self.search([('name', '=', ZNPREF)])
        #_logger.debug("Delivery found %d (%s)", delivery.id, delivery.name)
            for edi_line in content.splitlines():
                P2ARID = edi_line[21:35].strip() #Product ID
                if sl.product_code == P2ARID:
                    _logger.info('match')
                    P2ACTS = int(edi_line[254:265].strip())
                    sl.product_qty = P2ACTS
                    continue
                else:
                    _logger.info('no match on %s and %s', sl.product_code, P2ARID)
              
                # map inventory lines to relevant fields
            _logger.info('finished running through %s', sl.product_code)
            continue

        return True
