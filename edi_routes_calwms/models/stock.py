import datetime
import logging
from odoo import api, _
from odoo import models, fields
from odoo.exceptions import except_orm
from odoo.addons.edi_tools.models.edi_mixing import EDIMixin

_logger = logging.getLogger(__name__)

class stock_picking(models.Model, EDIMixin):
    _inherit = "stock.picking"

    #Export Section
    @api.model
    def valid_for_edi_export_calwms(self, record):
        if record.state != 'assigned':
            return False
        return True

    @api.multi
    def send_edi_export_calwms(self, partner_id):
        valid_pickings = self.filtered(self.valid_for_edi_export_calwms)
        invalid_pickings = [p for p in self if p not in valid_pickings]
        if invalid_pickings:
            raise except_orm(_('Invalid pickings in selection!'), _('The following pickings are invalid, please remove from selection. %s') % (map(lambda record: record.name, invalid_pickings)))

        for picking in valid_pickings:
            content = picking.edi_export_calwms(picking, edi_struct=None)
            result = self.env['edi.tools.edi.document.outgoing'].create_from_content(picking.name, content, partner_id.id, 'stock.picking', 'send_edi_export_calwms', type='STRING')
            if not result:
                raise except_orm(_('EDI creation failed!', _('EDI processing failed for the following picking %s') % (picking.name)))
        return True

    @api.model
    def edi_export_calwms(self, delivery, edi_struct=None):
        co_id = 1
        d = datetime.datetime.strptime(delivery.scheduled_date, "%Y-%m-%d %H:%M:%S")
        #V08 : d = datetime.datetime.strptime(delivery.min_date, "%Y-%m-%d %H:%M:%S")
        edi_doc = ''
        picking_type = delivery.picking_type_id.code #incoming outgoing internal

        # Basic header fields
        ZNRECT = 'ZEN' # 1 3
        ZNVERS = '2' # 4 4
        if picking_type == 'incoming':
            ZNTYPE = '001' # 22 24
        else:
            ZNTYPE = '011'
        ZNPREF = delivery.name # 25  59
        ZNGU_D = d.strftime("%Y%m%d") #desired delivery date CCYYMMDD # 113  120 for outbound
        ZNGT_D = d.strftime("%Y%m%d") #planned date CCYYMMDD # 141 148 for inbound
        ZNRAID = str(delivery.partner_id.id) # 169  182
        if picking_type == 'incoming':
            header = ZNRECT.ljust(3) + ZNVERS.ljust(1) + ''.ljust(17) + ZNTYPE.ljust(3) + ZNPREF.ljust(35) + ''.ljust(81) + ZNGT_D.ljust(8) + ''.ljust(20) + ZNRAID.ljust(14)
        else:
            header = ZNRECT.ljust(3) + ZNVERS.ljust(1) + ''.ljust(17) + ZNTYPE.ljust(3) + ZNPREF.ljust(35) + ''.ljust(53) + ZNGU_D.ljust(8) + ''.ljust(48) + ZNRAID.ljust(14)
        edi_doc = edi_doc +header + '\n'

        # Line items
        line_counter = 1
        for line in delivery.move_lines:
            product = self.env['product.product'].browse(line.product_id.id)

            ZRRECT = 'ZRG'
            ZRVERS = '2'
            ZRADID = str(delivery.partner_id.id).ljust(14)
            ZRZRPR = str(line_counter).ljust(35)
            ZRTYPE = ZNTYPE.ljust(3)
            ZRARID = str(product.barcode).ljust(14)
            ZRAVEO = str(int(line.product_uom_qty))

            #Write the original line sequence to the move line for matching on import
            line.write({'edi_sequence': "%06d" % (line_counter,)})

            line_counter = line_counter + 1
            line_content = ZRRECT + ZRVERS + ZRADID + ''.ljust(6) + ZRTYPE + ZRZRPR + ''.ljust(3) + ZRARID + ''.ljust(169) + ZRAVEO.ljust(6)
            edi_doc = edi_doc +line_content + '\n'

        # Return the result
        return edi_doc


    #Import section
    @api.model
    def edi_import_calwms_validator(self, document_ids):
        _logger.debug("Validating CALwms document")
        return True

    @api.model
    def receive_edi_import_calwms(self, document_ids):
        document = self.env['edi.tools.edi.document.incoming'].browse(document_ids)
        document.ensure_one()
        return self.edi_import_calwms(document)

    @api.model
    def edi_import_calwms(self, document):
        content = document.content
        i = 0
        for lin in content.splitlines():
            if i == 0:
                ZNPREF = lin[30:64].strip()
                break

        delivery = self.search([('name', '=', ZNPREF)])
        _logger.debug("Delivery found %d (%s)", delivery.id, delivery.name)

        if not delivery.pack_operation_ids:
            _logger.info("No pack_operation_ids, executing do_prepare_partial()")
            delivery.do_prepare_partial()

        processed_ids = []
        for edi_line in content.splitlines():
            # map line to relevant fields
            if i == 0:
                i += 1
                continue

            if i > 0:
                ZRZRPR = edi_line[34:68].strip() #Line Reference
                ZRARID = edi_line[72:85].strip() #Item Code
                ZRVVDT = edi_line[144:152].strip() #Minimal BBD
                ZRPHAN = edi_line[289:295].strip() #QTY Delivered in SKU

            move_line = delivery.move_lines.filtered(lambda ml: ml.edi_sequence == ZRZRPR)
            if len(move_line.linked_move_operation_ids) == 0:
                raise except_orm(_('No pack operation found!'), _('No pack operation was found for edi sequence %s in picking %s (%d)') % (ZRZRPR, delivery.name, delivery.id))
            pack_operation = move_line.linked_move_operation_ids[0].operation_id
            if pack_operation.remaining_qty >= 0.0:
                pack_operation.with_context(no_recompute=True).write({'product_qty': ZRPHAN})
                _logger.info("Replaced QTY with EDI Value ZRPHAN")
            elif pack_operation.remaining_qty*(-1) >= float(ZRPHAN):
                pack_operation.with_context(no_recompute=True).write({'product_qty': pack_operation.product_qty + float(ZRPHAN)})
                _logger.info("Added EDI ZRPHAN to QTY from available remaining QTY")
            else:
               raise except_orm(_('More delivered than requested!'), _('pack operation %s requested %s, but only %s remained.') % (pack_operation, ZRPHAN, pack_operation.remaining_qty))
            processed_ids.append(pack_operation.id)

        # delete the others pack operations, they will be included in the backorder
        unprocessed_ids = self.env['stock.pack.operation'].search(['&', ('picking_id', '=', delivery.id), '!', ('id', 'in', processed_ids)])
        unprocessed_ids.unlink()

        # execute the transfer of the picking
        delivery.do_transfer()

        return True
