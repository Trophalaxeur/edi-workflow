import datetime
import logging
import xml.etree.cElementTree as ET
import xmltodict

from openerp import models, fields, api, _
from openerp.exceptions import except_orm
from openerp.addons.edi_tools.models.exceptions import EdiIgnorePartnerError, EdiValidationError

from builder import EssersEdiBuilder

_logger = logging.getLogger(__name__)


class mrp_production(models.Model):
    _inherit = "mrp.production"

    crossdock_overrule = fields.Selection([('Y', 'Yes'), ('N', 'No')], copy=False)
    groupage_overrule = fields.Selection([('Y', 'Yes'), ('N', 'No')], copy=False)
    number_of_pallets = fields.Integer(string='Number Of Pallets')

    @api.model
    def valid_for_edi_export_essers_mrp(self, record):
        if record.state not in ('confirmed','ready','in_production'):
            _logger.info("record.state not confirmed, ready or in_production , error")
            return False
        _logger.info("valid for export")
        return True

    @api.multi
    def send_edi_export_essers_mrp(self, partner_id):
        valid_mos = self.filtered(self.valid_for_edi_export_essers_mrp)
        invalid_mos = [p for p in self if p not in valid_mos]
        if invalid_mos:
            raise except_orm(_('Invalid manufacturing orders in selection!'), _('The following MO are invalid, please remove from selection. %s') % (map(lambda record: record.name, invalid_mos)))

        for mo in valid_mos:
            content = mo.edi_export_essers_mrp(mo, None)
            result = self.env['edi.tools.edi.document.outgoing'].create_from_content(mo.name, content, partner_id.id, 'mrp.production', 'send_edi_export_essers_mrp', type='XML')
            if not result:
                raise except_orm(_('EDI creation failed!', _('EDI processing failed for the following picking %s') % (picking.name)))
        return True

    @api.model
    def edi_export_essers_mrp(self, mo, edi_struct=None):

        sale_order = False
        if mo.origin:
            sale_order = self.env['sale.order'].search([('name', '=', mo.origin)], limit=1)

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
        ET.SubElement(temp, "DELIV_NUMB").text = mo.name.replace('/', '_')

        # not available on MO
        # ET.SubElement(temp, "EXTDELV_NO").text = mo.order_reference

        mo._build_partner_header(header)
        mo._build_delivery_date_header(header)

        # Line items
        i = 0
        for line in mo.move_lines:

            i = i + 100
            
            # Write this EDI sequence to the delivery for referencing the response
            line.write({'edi_sequence': "%06d" % (i,)})
            
            if line.reserved_availability == 0:
                _logger.info("reserved == 0, skipping line")
                continue

            if i == 100:
                temp = ET.SubElement(header, "E1BPEXT")
                temp.set('SEGMENT', '1')
                ET.SubElement(temp, "PARAM").text = mo.name.replace('/', '_') + "__" + "%06d" % (i,)
                ET.SubElement(temp, "FIELD").text = "END"
                ET.SubElement(temp, "VALUE").text = mo.product_id.name.upper()
                ET.SubElement(temp, "ROW").text = "1" 
                
                temp = ET.SubElement(header, "E1BPEXT")
                temp.set('SEGMENT', '1')
                ET.SubElement(temp, "PARAM").text = mo.name.replace('/', '_') + "__" + "%06d" % (i,)
                ET.SubElement(temp, "FIELD").text = "QTY"
                ET.SubElement(temp, "VALUE").text = str(int(mo.product_qty))
                ET.SubElement(temp, "ROW").text = "1"
            
            temp = ET.SubElement(header, "E1BPOBDLVITEM")
            temp.set('SEGMENT', '1')
            ET.SubElement(temp, "DELIV_NUMB").text = mo.name.replace('/', '_')
            ET.SubElement(temp, "ITM_NUMBER").text = "%06d" % (i,)
            ET.SubElement(temp, "MATERIAL").text = line.product_id.name.upper()
            ET.SubElement(temp, "DLV_QTY_STOCK").text = str(int(line.reserved_availability))

            ET.SubElement(temp, "BOMEXPL_NO").text = '0'

            temp = ET.SubElement(header, "E1BPOBDLVITEMORG")
            temp.set('SEGMENT', '1')
            ET.SubElement(temp, "DELIV_NUMB").text = mo.name.replace('/', '_')
            ET.SubElement(temp, "ITM_NUMBER").text = "%06d" % (i,)
            
            # What about storage locations ?
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
    def _build_partner_header(self, header_element):
        builder = EssersEdiBuilder()
        # sold-to
        company = self.env['res.company'].search([('id','=',self.company_id.id)], limit=1)

        if company:
            builder.build_e1bpdlvpartner_element(header_element, '1', 'AG', company.partner_id.expertm_reference)
            builder.build_e1bpadr1_element(header_element,
                                           sequence='1',
                                           name=company.partner_id.name,
                                           city=company.partner_id.city,
                                           zipcode=company.partner_id.zip,
                                           street1=company.partner_id.street,
                                           street2=company.partner_id.street2,
                                           country=company.partner_id.country_id.code,
                                           language=company.partner_id.lang[3:5])

    @api.multi
    def _build_delivery_date_header(self, header_element):
        EssersEdiBuilder().build_e1bpdlvdeadln_element(header_element, self._name_edi(), self.date_planned, 'CET')

    @api.model
    def edi_import_essers_mrp_validator(self, document_ids):
        _logger.debug("Validating Essers MRP document")

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
        mo = self.search([('name', '=', content['DELIVERY'].replace('_', '/'))], limit=1)
        if not mo:
            raise EdiValidationError('Could not find the referenced MO: {!s}.'.format(content['DELIVERY']))

        if mo.state == 'done':
            raise EdiValidationError("MO already processed.")

        if mo.state == 'cancel':
            raise EdiValidationError("MO was manually cancelled.")

        lines_without_sequence = [ml for ml in mo.move_lines if not ml.edi_sequence]
        if lines_without_sequence:
            raise EdiValidationError("MO %s has lines without edi_sequence" % (mo.name))

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

            move_line = [x for x in mo.move_lines if x.edi_sequence == edi_line['DELIV_ITEM']]
            if not move_line:  # skip BOM explosion lines
                continue
            move_line = move_line[0]
            if move_line.product_id.name.upper() != edi_line['MATERIAL'].upper():
                raise EdiValidationError('Line mentioned with EDI sequence {!s} has a different material.'.format(edi_line['DELIV_ITEM']))

        _logger.debug("Essers document valid")
        return True

    @api.model
    def receive_edi_import_essers_mrp(self, document_ids):
        document = self.env['edi.tools.edi.document.incoming'].browse(document_ids)
        document.ensure_one()
        return self.edi_import_essers_mrp(document)

    @api.model
    def edi_import_essers_mrp(self, document):
        content = xmltodict.parse(document.content)
        content = content['SHP_OBDLV_CONFIRM_DECENTRAL02']['IDOC']['E1SHP_OBDLV_CONFIRM_DECENTR']

        mo = self.search([('name', '=', content['DELIVERY'].replace('_', '/').replace('PCK', 'MO'))])
        _logger.debug("MO found %d (%s)", mo.id, mo.name)

        # cast the line items to a list if there's only 1 item
        if not isinstance(content['E1BPOBDLVITEMCON'], list):
            content['E1BPOBDLVITEMCON'] = [content['E1BPOBDLVITEMCON']]

        qty_produced =  mo.product_qty
        qty_produced_changed = False

        for edi_line in content['E1BPOBDLVITEMCON']:
            move_line = mo.move_lines.filtered(lambda ml: ml.edi_sequence == edi_line['DELIV_ITEM'])
            quant_qty = 0.0
            for quant in move_line.reserved_quant_ids:
                quant_qty += quant.qty
            if quant_qty == float(edi_line['DLV_QTY_IMUNIT']):
                _logger.info("Line %s quantity matches requested production, proceeding", move_line.edi_sequence)
            elif (quant_qty % float(edi_line['DLV_QTY_IMUNIT']) == 0):
                _logger.info("Line %s quantity is less than the requested production, adjusting production", move_line.edi_sequence)
                if qty_produced_changed == False:
                    qty_produced = quant_qty / float(edi_line['DLV_QTY_IMUNIT'])
                    qty_produced_changed = True
                else:
                    if quant_qty / float(edi_line['DLV_QTY_IMUNIT']) == qty_produced:
                        _logger.info("Line matches changed production quantity, proceeding")
                    else:
                        raise except_orm(_('Production Qty mismatch!'), _('Produced quantities are not in line with BoM'))
                _logger.info("new production value is %d", qty_produced)

        wiz_obj = self.env['mrp.product.produce']
        ctx = dict(self.env.context, active_id=mo.id)
        produce_wiz = wiz_obj.with_context(ctx).create({'product_qty': qty_produced})
        produce_wiz.do_produce()

        _logger.info("qty produced = %d", qty_produced)

        return True
