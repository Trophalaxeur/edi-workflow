import datetime
import logging
import xml.etree.cElementTree as ET
import xmltodict

from openerp import models, fields, api, _
from openerp.exceptions import except_orm
from openerp.addons.edi_tools.models.exceptions import EdiIgnorePartnerError, EdiValidationError

_logger = logging.getLogger(__name__)

class sale_order(models.Model):
    _inherit = "sale.order"
    
    @api.model
    def edi_import_order_xml_validator(self, document_ids):
        _logger.debug("Validating XML document")

        # Read the EDI Document
        edi_db = self.env['edi.tools.edi.document.incoming']
        document = edi_db.browse(document_ids)
        document.ensure_one()

        # Convert the document to JSON
        try:
            content = xmltodict.parse(document.content)
            #valid = content[InitialPurchaseOrder]
            #valid = content[InitialPurchaseOrder][PurchaseOrderHeader]
        except Exception:
            raise EdiValidationError('Content is not valid XML or the structure deviates from what is expected.')

        if not 'InitialPurchaseOrder' in content:
            _logger.debug("XML Order document invalid, no InitialPurchaseOrder segment")
            raise EdiValidationError('XML Order document invalid, no InitialPurchaseOrder segment')

        if not 'DestinationName1' in content['InitialPurchaseOrder']['PurchaseOrderHeader']['IdDestination']:
            _logger.debug("XML Order document invalid, no Destination Name in IdDestination")
            raise EdiValidationError('XML Order document invalid, no Destination Name in IdDestination')
        else:
            header = content['InitialPurchaseOrder']['PurchaseOrderHeader']
            delivery_partner = self.env['res.partner'].search([('name','=',header['IdDestination']['DestinationName1'])])
            _logger.info("XML Delivery Partner: %s",header['IdDestination']['DestinationName1'])

            if not delivery_partner:
                raise EdiValidationError('Delivery Partner not found')

        _logger.debug("XML Order document valid")
        return True

    @api.model
    def receive_edi_import_order_xml(self, document_ids):
        document = self.env['edi.tools.edi.document.incoming'].browse(document_ids)
        document.ensure_one()
        return self.edi_import_order_xml(document)

    @api.model
    def edi_import_order_xml(self, document):
        content = xmltodict.parse(document.content)
        header = content['InitialPurchaseOrder']['PurchaseOrderHeader']
        delivery_partner = self.env['res.partner'].search([('name','=',header['IdDestination']['DestinationName1'])])
        _logger.info("Partner Found: %s", delivery_partner.id)
        
        param = {}

        param['partner_id'] = document.partner_id.id
        param['partner_shipping_id'] = delivery_partner.id
        param['partner_invoice_id'] = document.partner_id.id
        param['client_order_ref'] = header['IdOrderData']['PurchaseOrderNumber'] + ' ' + header['IdOther']['Reference']

        if header['IdOther']['DeliveryDate'] != None:
            _logger.info("Requested Delivery Date Set")
            req_date = header['IdOther']['DeliveryDate'][6:] + '-' + header['IdOther']['DeliveryDate'][3:5] + '-' + header['IdOther']['DeliveryDate'][:2] + ' 05:00:00'
            param['requested_date'] = req_date
        else:
            _logger.info("No Requested Delivery Date specified")
       
        param['order_line'] = []
        
        for line in content['InitialPurchaseOrder']['PurchaseOrderRows']['IdRows']:
            if line == 'RowNumber':
                singleline = content['InitialPurchaseOrder']['PurchaseOrderRows']
                _logger.info("Single Line Detected, processing differently")
                break
            else:
                if 'BarCode' in line:
                    detail = {}
                    product = self.env['product.product'].search([('ean13','=',line['BarCode'])]).id
                    if product:
                        detail['product_id'] = product
                        detail['product_uom_qty'] = float(line['Quantity'])
                        order_line = []
                        order_line.extend([0])
                        order_line.extend([False])
                        order_line.append(detail)
                        param['order_line'].append(order_line)
                        _logger.info("Product Found: %s", detail['product_id'])
                    else:
                        _logger.info("Product Not Found: %s", line['BarCode'])
                        raise EdiValidationError('Barcode not found: %s' % line['BarCode'])

                else:
                    _logger.info("No BarCode element in line")
        
        #if singleline:
        #    if 'BarCode' in singleline:
        #        detail = {}
        #        detail['product_id'] =  self.env['product.product'].search([('ean13','=',singleline['BarCode'])]).id
        #        detail['product_uom_qty'] = float(line['Quantity'])
        #        order_line = []
        #        order_line.extend([0])
        #        order_line.extend([False])
        #        order_line.append(detail)
        #        param['order_line'].append(order_line)
        #        _logger.info("Single Product Found: %s", detail['product_id'])

        sid = self.create(param)
        so = self.browse(sid.id)[0]

        return so.name
