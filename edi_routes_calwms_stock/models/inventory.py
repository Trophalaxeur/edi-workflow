import datetime
import logging
import datetime
import pytz

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
        
        return True

    @api.model
    def create_stock_inventory(self, content):
        _logger.info('prepping inventory!')
        param = {}
        inv = self.create_inventory(param, content)
        _logger.info('created inventory! %s', str(inv))
        return str(inv)

    def create_inventory(self, param, content):
        # Prepare the call to create an Inventory
        _logger.info('prepping!!')
        param['name'] = 'Inventory '+str(pytz.utc.localize(datetime.datetime.utcnow()))[:19]
        param['exhausted'] = 'True'
        iid = self.create(param)
        iid.action_start()
        Product = self.env['product.product']
        Lot = self.env['stock.production.lot']
        for sl in iid.line_ids: 
            _logger.debug('start lookup %s', sl.product_code)
            if sl.package_id:
                continue
            for edi_line in content.splitlines():
                P2ARID = edi_line[21:35].strip() #Product ID
                if not P2ARID:
                    _logger.debug('no product in line %s', sl.product_code)
                    continue
                if sl.product_code == P2ARID:
                    _logger.debug('Product match with EDI %s', sl.product_code)
                    P2ACTS = int(edi_line[254:265].strip())
                    P2PTID = str(edi_line[49:84].strip())
                    P2VVDT = str(edi_line[135:143].strip())
                    BBD = P2VVDT[0:4]+'-'+P2VVDT[4:6]+'-'+P2VVDT[6:8]
                    CurrentLots = Lot.search([('name', '=', P2PTID)])
                    Match = 0
                    #first we check if the lot mentioned in the EDI file exists in Odoo
                    for CurrentLot in CurrentLots:
                        #for lots in Odoo with the name from the EDI file, find the one with the matching product.
                        if CurrentLot.product_id == sl.product_id and CurrentLot.name == str(P2PTID) and Match == 0:
                            Match = 1
                            _logger.debug('Matching lot! %s', sl.product_code)
                            #if the lot exists, check if it is the one mentioned in the inventory line and adjust it's quantity.
                            if sl.prod_lot_id == CurrentLot:
                                sl.product_qty = P2ACTS
                                break
                            #if there is no lot mentioned on the inventory line, assign the lot from EDI to it.
                            if not sl.prod_lot_id:
                                sl.prod_lot_id = CurrentLot
                                sl.product_qty = P2ACTS
                            
                    #if the lot from the EDI does not exist in Odoo we create it and link it to the inventory line 
                    if Match == 0:
                        sl.prod_lot_id = Lot.create({'name': str(P2PTID),'product_id': sl.product_id.id, 'product_qty': float(P2ACTS)})
                        _logger.debug('No matching lot, created lot for %s', sl.product_code)
                        sl.prod_lot_id.use_date = BBD
                        sl.product_qty = P2ACTS
                    
                  
                    continue
                else:
                    P2ACTS = int(edi_line[254:265].strip())
                    _logger.debug('else, no match %s', sl.product_code)
                    continue
                continue 
            _logger.debug('finished running through %s', sl.product_code)
            continue

        return iid.name
