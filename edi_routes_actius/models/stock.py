import datetime
import logging
import xml.etree.cElementTree as ET
import xmltodict

from openerp import models, fields, api, _
from openerp.exceptions import except_orm
from openerp.addons.edi_tools.models.exceptions import EdiIgnorePartnerError, EdiValidationError

from builder import ActiusEdiBuilder

_logger = logging.getLogger(__name__)


class stock_picking(models.Model):
    _inherit = "stock.picking"

    crossdock_overrule = fields.Selection([('Y', 'Yes'), ('N', 'No')], copy=False)
    groupage_overrule = fields.Selection([('Y', 'Yes'), ('N', 'No')], copy=False)
    number_of_pallets = fields.Integer(string='Number Of Pallets')

    @api.model
    def valid_for_edi_export_actius(self, record):
        if record.state not in ('partially_available','assigned'):
            _logger.info("record.state not partially_available or assigned, error")
            return False
        if not record.partner_id.expertm_reference:
            _logger.info("partner_id.expertm_reference empty")
            return False
        if record.origin:
            orderref = record.origin.partition(':')
            order = self.env['sale.order'].search([('name', '=', orderref[0])])
            if not order.partner_id.expertm_reference:
                _logger.info("order.partner_id.expertm_reference empty")
                return False
        for line in record.move_lines:
            if line.reserved_availability > line.product_qty:
                _logger.info("reserved_availability > line.product_qty")
                return False
        _logger.info("valid for export")
        return True

    @api.multi
    def send_edi_export_actius(self, partner_id):
        valid_pickings = self.filtered(self.valid_for_edi_export_actius)
        invalid_pickings = [p for p in self if p not in valid_pickings]
        if invalid_pickings:
            raise except_orm(_('Invalid pickings in selection!'), _('The following pickings are invalid, please remove from selection. %s') % (map(lambda record: record.name, invalid_pickings)))

        for picking in valid_pickings:
            content = picking.edi_export_actius(picking, None)
            result = self.env['edi.tools.edi.document.outgoing'].create_from_content(picking.name, content, partner_id.id, 'stock.picking', 'send_edi_export_actius', type='XML')
            if not result:
                raise except_orm(_('EDI creation failed!', _('EDI processing failed for the following picking %s') % (picking.name)))
        return True

    @api.model
    def edi_export_actius(self, delivery, edi_struct=None):

        sale_order = False
        if delivery.origin:
            sale_order = self.env['sale.order'].search([('name', '=', delivery.origin)], limit=1)

        # Actual EDI conversion of the delivery
        root = ET.Element("SHP_OBDLV_SAVE_REPLICA02")
        idoc = ET.SubElement(root, "IDOC")
        idoc.set('BEGIN', '1')
        header = ET.SubElement(idoc, "EDI_DC40")
        header.set('SEGMENT', '1')
        ET.SubElement(header, "MESTYP").text = 'SHP_OBDLV_SAVE_REPLICA'
        header = ET.SubElement(idoc, "E1SHP_OBDLV_SAVE_REPLICA")
        header.set('SEGMENT', '1')

        temp = ET.SubElement(header, "E1BPOBDLVHDR")
        temp.set('SEGMENT', '1')
        ET.SubElement(temp, "DELIV_NUMB").text = delivery.name.replace('/', '_')
        ET.SubElement(temp, "EXTDELV_NO").text = delivery.order_reference

        if delivery.incoterm:
            if delivery.incoterm.code == 'EXW':
                ET.SubElement(temp, "ROUTE").text = 'PICKUP'
            else:
                ET.SubElement(temp, "ROUTE").text = 'REGULAR'
        _logger.info("building partner headersx")
        delivery._build_partner_header_actius(header)
        _logger.info("building delivery date headers")
        delivery._build_delivery_date_header_actius(header)
        delivery._build_crossdock_overrule_header(header)
        delivery._build_groupage_overrule_header(header)
        delivery._build_instruction_header(header)
        delivery._build_priority_header(header)

        # Line items
        i = 0
        for line in delivery.move_lines:
            
            #ADJUSTED LOGIC FOR ACTIUS:
            #IF LINE NOT IN STOCK > DONT WRITE LINE COUNTER, CONTINUE TO NEXT LINE

            if line.reserved_availability == 0:
                _logger.info("reserved == 0, skipping line")
                continue
            
            i = i + 100
            
            # Write this EDI sequence to the delivery for referencing the response
            line.write({'edi_sequence': "%06d" % (i,)})
            

            temp = ET.SubElement(header, "E1BPOBDLVITEM")
            temp.set('SEGMENT', '1')
            ET.SubElement(temp, "DELIV_NUMB").text = delivery.name.replace('/', '_')
            ET.SubElement(temp, "ITM_NUMBER").text = "%06d" % (i,)
            ET.SubElement(temp, "MATERIAL").text = line.product_id.name.upper()
            ET.SubElement(temp, "DLV_QTY_STOCK").text = str(int(line.reserved_availability))

            if not line.product_id.bom_ids:
                _logger.info("no bom product")
                ET.SubElement(temp, "BOMEXPL_NO").text = '0'
            elif line.product_id.bom_ids[0].picking_type == 'pickpack':
                _logger.info("bom product, type pickpack, sending detail")
                ET.SubElement(temp, "BOMEXPL_NO").text = '5'
                j = i
                for bom in line.product_id.bom_ids[0].bom_line_ids:
                    j = j + 1
                    temp = ET.SubElement(header, "E1BPOBDLVITEM")
                    temp.set('SEGMENT', '1')
                    ET.SubElement(temp, "DELIV_NUMB").text = delivery.name.replace('/', '_')
                    ET.SubElement(temp, "ITM_NUMBER").text = "%06d" % (j,)
                    ET.SubElement(temp, "MATERIAL").text = bom.product_id.name.upper()
                    ET.SubElement(temp, "DLV_QTY_STOCK").text = str(int(line.reserved_availability * bom.product_qty))
                    ET.SubElement(temp, "BOMEXPL_NO").text = '6'

                    temp = ET.SubElement(header, "E1BPOBDLVITEMORG")
                    temp.set('SEGMENT', '1')
                    ET.SubElement(temp, "DELIV_NUMB").text = delivery.name.replace('/', '_')
                    ET.SubElement(temp, "ITM_NUMBER").text = "%06d" % (j,)
                    ET.SubElement(temp, "STGE_LOC").text = '0'
            else:
                _logger.info("bom producti, manufacture, no details")
                ET.SubElement(temp, "BOMEXPL_NO").text = '0'

            temp = ET.SubElement(header, "E1BPOBDLVITEMORG")
            temp.set('SEGMENT', '1')
            ET.SubElement(temp, "DELIV_NUMB").text = delivery.name.replace('/', '_')
            ET.SubElement(temp, "ITM_NUMBER").text = "%06d" % (i,)
            if not line.storage_location:
                ET.SubElement(temp, "STGE_LOC").text = '0'
            else:
                ET.SubElement(temp, "STGE_LOC").text = line.storage_location

            line._build_line_customerinfo(header, i)


        return root

    @api.multi
    def _name_edi(self, padding_end=0):
        self.ensure_one()
        return self.name.replace('/', '_') + (padding_end * '0')

    @api.multi
    def _build_partner_header_actius(self, header_element):
        _logger.info("Building Partner HeaderX")
        builder = ActiusEdiBuilder()
        sale_order = self.env['sale.order'].search([('name', '=', self.origin)], limit=1)
        # sent-from
        # if sale_order.partner_id.property_product_pricelist = 4 set sale_order.partner  as sender
        # else : send from own company
        #_logger.info("Building Header")
        #if sale_order:
        #    if sale_order.partner_id.property_product_pricelist.id == 4:
        #        builder.build_e1bpdlvpartner_element(header_element, '1', 'RG', sale_order.partner_id.expertm_reference)
        #        builder.build_e1bpadr1_element(header_element,
        #                                       sequence='1',
        #                                       name=sale_order.partner_id.name,
        #                                       city=sale_order.partner_id.city,
        #                                       zipcode=sale_order.partner_id.zip,
        #                                       street1=sale_order.partner_id.street,
        #                                       street2=sale_order.partner_id.street2,
        #                                       country=sale_order.partner_id.country_id.code,
        #                                       language=sale_order.partner_id.lang[3:5])
        #        _logger.info("Without Own Logistics, RG = SO Partner")
        #    else:
        #        builder.build_e1bpdlvpartner_element(header_element, '1', 'RG', '99999')
        #        builder.build_e1bpadr1_element(header_element,
        #                                       sequence='1',
        #                                       name=self.company_id.name,
        #                                       city=self.company_id.city,
        #                                       zipcode=self.company_id.zip,
        #                                       street1=self.company_id.street,
        #                                       street2=self.company_id.street2,
        #                                       country=self.company_id.country_id.code,
        #                                       language='US')
        #        _logger.info("With Own Logistics, RG = Lutec")

        # sold-to
        # if pricelist = 4, sold to = ship to, else sold to is sold to
        if sale_order:
            if sale_order.partner_id.property_product_pricelist.id == 4:
                builder.build_e1bpdlvpartner_element(header_element, '1', 'AG', self.partner_id.expertm_reference)
                builder.build_e1bpadr1_element(header_element,
                                               sequence='1',
                                               name=self.partner_id.name,
                                               city=self.partner_id.city,
                                               zipcode=self.partner_id.zip,
                                               street1=self.partner_id.street,
                                               street2=self.partner_id.street2,
                                               country=self.partner_id.country_id.code,
                                               language=self.partner_id.lang[3:5])
            else:
                builder.build_e1bpdlvpartner_element(header_element, '1', 'AG', sale_order.partner_id.expertm_reference)
                builder.build_e1bpadr1_element(header_element,
                                               sequence='1',
                                               name=sale_order.partner_id.name,
                                               city=sale_order.partner_id.city,
                                               zipcode=sale_order.partner_id.zip,
                                               street1=sale_order.partner_id.street,
                                               street2=sale_order.partner_id.street2,
                                               country=sale_order.partner_id.country_id.code,
                                               language=sale_order.partner_id.lang[3:5])
        # ship-to
        builder.build_e1bpdlvpartner_element(header_element, '2', 'WE', self.partner_id.expertm_reference)
        builder.build_e1bpadr1_element(header_element,
                                       sequence='2',
                                       name=self.partner_id.name,
                                       city=self.partner_id.city,
                                       zipcode=self.partner_id.zip,
                                       street1=self.partner_id.street,
                                       street2=self.partner_id.street2,
                                       country=self.partner_id.country_id.code,
                                       language=self.partner_id.lang[3:5])

    @api.multi
    def _build_delivery_date_header_actius(self, header_element):
        _logger.info("Sale Header Requested Date Check")
        sale_order = self.env['sale.order'].search([('name', '=', self.origin)], limit=1)
        if sale_order and sale_order.requested_date:
            _logger.info("Requested Date Filled In")
            ActiusEdiBuilder().build_e1bpdlvdeadln_element(header_element, self._name_edi(), self.min_date, 'CET')
            d = 1
        else:
            _logger.info("No Requested Date Supplied")
            ActiusEdiBuilder().build_e1bpdlvdeadln_element(header_element, self._name_edi(), self.date, 'CET')
            d = 2

    @api.multi
    def _build_crossdock_overrule_header(self, header_element):
        if self.crossdock_overrule:
            ActiusEdiBuilder().build_e1bptext_element(header_element, self._name_edi(6), '0', 'SSP', self.crossdock_overrule)

    @api.multi
    def _build_groupage_overrule_header(self, header_element):
        if self.groupage_overrule:
            ActiusEdiBuilder().build_e1bptext_element(header_element, self._name_edi(6), '0', 'SOP', self.groupage_overrule)

    @api.multi
    def _build_instruction_header(self, header_element):
        if self.instruction_1:
            ActiusEdiBuilder().build_e1bptext_element(header_element, self._name_edi(6), '001', 'CMT', self.instruction_1[:70])
        if self.instruction_2:
            ActiusEdiBuilder().build_e1bptext_element(header_element, self._name_edi(6), '002', 'CMT', self.instruction_2[:70])

    @api.multi
    def _build_priority_header(self, header_element):
        if self.priority == '3':
            ActiusEdiBuilder().build_e1bptext_element(header_element, self._name_edi(6), '0', 'SBY', '1')

    @api.model
    def edi_import_actius_validator(self, document_ids):
        _logger.debug("Validating Actius document")

        # Read the EDI Document
        edi_db = self.env['edi.tools.edi.document.incoming']
        document = edi_db.browse(document_ids)
        document.ensure_one()

        # Convert the document to JSON
        try:
            content = xmltodict.parse(document.content)
            content = content['SHP_OBDLV_CONFIRM_DECENTRAL02']['IDOC']['E1SHP_OBDLV_CONFIRM_DECENTR']
        except Exception:
            raise EdiValidationError('Content is not valid XML or the structure deviates from what is expected.')

        # Check if we can find the delivery
        delivery = self.search([('name', '=', content['DELIVERY'].replace('_', '/'))], limit=1)
        if not delivery:
            raise EdiValidationError('Could not find the referenced delivery: {!s}.'.format(content['DELIVERY']))

        if delivery.state == 'done':
            raise EdiValidationError("Delivery already transfered.")

        if delivery.state == 'cancel':
            raise EdiValidationError("Delivery was manually cancelled.")

        lines_without_sequence = [ml for ml in delivery.move_lines if not ml.edi_sequence]
        #if lines_without_sequence:
        #    raise EdiValidationError("Delivery %s has lines without edi_sequence" % (delivery.name))

        # Check if all the line items match
        if not content['E1BPOBDLVITEMCON']:
            raise EdiValidationError('No line items provided')

        # cast the line items to a list if there's only 1 item
        if not isinstance(content['E1BPOBDLVITEMCON'], list):
            content['E1BPOBDLVITEMCON'] = [content['E1BPOBDLVITEMCON']]
        for edi_line in content['E1BPOBDLVITEMCON']:
            if not edi_line['DELIV_ITEM']:
                raise EdiValidationError('Line item provided without an identifier.')
            if not edi_line['MATERIAL']:
                raise EdiValidationError('Line item provided without a material identifier.')
            if not edi_line['DLV_QTY_IMUNIT']:
                raise EdiValidationError('Line item provided without a quantity.')
            if float(edi_line['DLV_QTY_IMUNIT']) == 0.0:
                raise EdiValidationError('Line item provided with quantity equal to zero (0.0).')

            move_line = [x for x in delivery.move_lines if x.edi_sequence == edi_line['DELIV_ITEM']]
            if not move_line:  # skip BOM explosion lines
                continue
            move_line = move_line[0]
            if move_line.product_id.name.upper() != edi_line['MATERIAL'].upper():
                raise EdiValidationError('Line mentioned with EDI sequence {!s} has a different material.'.format(edi_line['DELIV_ITEM']))
            if move_line.location_id.id != move_line.reserved_quant_ids[0].location_id.id:
                raise EdiValidationError('Location mismatch between source and quant reservation on line {!s}.'.format(edi_line['DELIV_ITEM']))

        _logger.debug("Actius document valid")
        return True

    @api.model
    def receive_edi_import_actius(self, document_ids):
        document = self.env['edi.tools.edi.document.incoming'].browse(document_ids)
        document.ensure_one()
        return self.edi_import_actius(document)

    @api.model
    def edi_import_actius(self, document):
        content = xmltodict.parse(document.content)
        content = content['SHP_OBDLV_CONFIRM_DECENTRAL02']['IDOC']['E1SHP_OBDLV_CONFIRM_DECENTR']

        delivery = self.search([('name', '=', content['DELIVERY'].replace('_', '/').replace('PCK', 'OUT'))])
        _logger.debug("Delivery found %d (%s)", delivery.id, delivery.name)

        if delivery.partner_id in document.flow_id.ignore_partner_ids:
            msg = "Detected that partner %s (%d) is in the ignore parter list for flow %s (%d)" % (delivery.partner_id.name, delivery.partner_id.id, document.flow_id.name, document.flow_id.id)
            raise EdiIgnorePartnerError(msg)

        if not delivery.pack_operation_ids:
            _logger.info("No pack_operation_ids, executing do_prepare_partial()")
            delivery.do_prepare_partial()

        # cast the line items to a list if there's only 1 item
        if not isinstance(content['E1BPOBDLVITEMCON'], list):
            content['E1BPOBDLVITEMCON'] = [content['E1BPOBDLVITEMCON']]

        processed_ids = []
        crt_ids = [] #a list of all CRT packs
        eur_ids = [] #a list of all pallets

        for edi_line in content['E1BPOBDLVITEMCON']:
            move_line = delivery.move_lines.filtered(lambda ml: ml.edi_sequence == edi_line['DELIV_ITEM'])
            if len(move_line.linked_move_operation_ids) == 0:
                raise except_orm(_('No pack operation found!'), _('No pack operation was found for edi sequence %s in picking %s (%d)') % (edi_line['DELIV_ITEM'], delivery.name, delivery.id))
            pack_operation = move_line.linked_move_operation_ids[0].operation_id
            if pack_operation.remaining_qty >= 0.0:
                pack_operation.with_context(no_recompute=True).write({'product_qty': edi_line['DLV_QTY_IMUNIT']})
                _logger.info("Replaced QTY with EDI DLV_QTY_IMUNIT")
            elif pack_operation.remaining_qty*(-1) >= float(edi_line['DLV_QTY_IMUNIT']):
                pack_operation.with_context(no_recompute=True).write({'product_qty': pack_operation.product_qty + float(edi_line['DLV_QTY_IMUNIT'])})
                _logger.info("Added DLV_QTY_IMUNIT to QTY from available remaining QTY")
            else:
                raise except_orm(_('More delivered than requested!'), _('pack operation %s requested %s, but only %s remained.') % (pack_operation, edi_line['DELIV_ITEM'], pack_operation.remaining_qty))
            # append pallets and packs to list
            if  edi_line['PACK_CODE']:
                if edi_line['PACK_CODE'] == 'EUR':
                    eur_ids.append(edi_line['PACK_NUMB'])
                    _logger.info("Added EUR to palletlist")
                if edi_line['PACK_CODE'] == 'CRT':
                    crt_ids.append(edi_line['PACK_NUMB'])
                    _logger.info("Added CRT to cartonlist")

            processed_ids.append(pack_operation.id)

        # write number of unique pallets and packs to OUT
        delivery.number_of_packages=len(list(set(crt_ids)))
        delivery.number_of_pallets=len(list(set(eur_ids)))

        # delete the others pack operations, they will be included in the backorder
        unprocessed_ids = self.env['stock.pack.operation'].search(['&', ('picking_id', '=', delivery.id), '!', ('id', 'in', processed_ids)])
        unprocessed_ids.unlink()

        # execute the transfer of the picking
        delivery.do_transfer()

        return True


class stock_move(models.Model):
    _inherit = "stock.move"

    edi_sequence = fields.Char(size=256, copy=False)
    storage_location = fields.Selection([
        ('0', 'Available'),
        ('B', 'Back To Back'),
        ('V', 'New Product Version'),
        ('Q', 'Quality Control')])

    @api.multi
    def _name_edi(self, line_num=0):
        self.ensure_one()
        return self.picking_id.name.replace('/', '_') + "%06d" % (line_num,)

    @api.multi
    def _build_line_customerinfo(self, header_element, line_num):
        sale_order = self.env['sale.order'].search([('name', '=', self.picking_id.origin)], limit=1)
        if sale_order:
            for customer_id in self.product_id.customer_ids:
                if customer_id.name.id == sale_order.partner_id.parent_id.id:
                    ActiusEdiBuilder().build_e1bptext_element(header_element, self._name_edi(line_num), '0', 'CIC', customer_id.product_code)
                elif customer_id.name.id == sale_order.partner_id.id:
                    ActiusEdiBuilder().build_e1bptext_element(header_element, self._name_edi(line_num), '0', 'CIC', customer_id.product_code)
