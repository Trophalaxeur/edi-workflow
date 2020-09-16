import datetime
import logging
from odoo import api, _, models
from odoo import models, fields
from odoo.exceptions import except_orm, ValidationError
from odoo.addons.edi_tools.models.edi_mixing import EDIMixin
from odoo.addons.edi_tools.models.exceptions import EdiIgnorePartnerError, EdiValidationError


_logger = logging.getLogger(__name__)

class stock_move(models.Model):
    _inherit = "stock.move"
    edi_sequence = fields.Char(size=256, copy=False)

class stock_picking(models.Model, EDIMixin):
    _inherit = "stock.picking"

    #Export Section
    @api.model
    def valid_for_edi_export_calwms(self, record):
        if record.state == 'cancel':
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
            result = self.env['edi.tools.edi.document.outgoing'].create_from_content(picking.name.replace(' ','_'), content, partner_id.id, 'stock.picking', 'send_edi_export_calwms', type='STRING')
            if not result:
                raise except_orm(_('EDI creation failed!', _('EDI processing failed for the following picking %s') % (picking.name)))
        return True

    @api.model
    def edi_export_calwms(self, delivery, edi_struct=None):
        co_id = 1
        d = datetime.datetime.strptime(delivery.scheduled_date, "%Y-%m-%d %H:%M:%S")
        edi_doc = ''
        picking_type = delivery.picking_type_id.code #incoming outgoing internal
        # Basic header fields
        ZNRECT = 'ZEN' # 1 3
        ZNVERS = '2' # 4 4
        if picking_type == 'incoming':
            ZNTYPE = '001' # 22 24
        else:
            ZNTYPE = '011'
        ZNPREF = delivery.name.replace(' ','_').ljust(35) # 25  59
        ZNGU_D = d.strftime("%Y%m%d").ljust(8) #desired delivery date CCYYMMDD # 113  120 for outbound
        ZNGT_D = d.strftime("%Y%m%d").ljust(8) #planned date CCYYMMDD # 141 148 for inbound
        ZNRAID = str(delivery.partner_id.id).ljust(14) # 169  182
        ZNRREF = delivery.origin.ljust(35) # 197  231
        ZNRNAM = delivery.partner_id.name[:35].ljust(80)	#Name of consignee 40+40	232	311
        ZNRADR = delivery.partner_id.street[:37].ljust(40)	#Address of consignee 40        312	351
        ZNRPCD = delivery.partner_id.zip[:10].ljust(10)	#ZIP of consignee 10            352	361
        ZNRPLT = delivery.partner_id.city[:35].ljust(40)	#City of consignee 40		362	401
        ZNRLAN = delivery.partner_id.country_id.code.ljust(3)	#Land of consignee 3    442	444

        if picking_type == 'incoming':
            header = ZNRECT + ZNVERS + ''.ljust(17) + ZNTYPE + ZNPREF + ''.ljust(81) + ZNGT_D + ''.ljust(20) + ZNRAID + ''.ljust(14) + ZNRREF + ZNRNAM + ZNRADR + ZNRPCD + ZNRPLT + ZNRLAN
        else:
            header = ZNRECT + ZNVERS + ''.ljust(17) + ZNTYPE + ZNPREF + ''.ljust(53) + ZNGU_D + ''.ljust(48) + ZNRAID + ''.ljust(14) + ZNRREF + ZNRNAM + ZNRADR + ZNRPCD + ZNRPLT + ZNRLAN
        edi_doc = edi_doc +header + '\n'

        # Line items
        line_counter = 1
        for line in delivery.move_lines:
            product = self.env['product.product'].browse(line.product_id.id)

            ZRRECT = 'ZRG'
            ZRVERS = '2'
            ZRADID = str(delivery.partner_id.id).ljust(14)
            ZRZRPR = str(line_counter).ljust(35)
            ZRTYPE = ZNTYPE
            ZRARID = str(product.default_code).ljust(14)
            ZRAVEO = str(int(line.product_uom_qty))

            #Write the original line sequence to the move line for matching on import
            line.write({'edi_sequence': "%06d" % (line_counter,)})

            line_counter = line_counter + 1
            line_content = ZRRECT + ZRVERS + ZRADID + ''.ljust(7) + ZRTYPE + ZRZRPR + ''.ljust(3) + ZRARID + ''.ljust(167) + ZRAVEO.ljust(6)
            edi_doc = edi_doc +line_content + '\n'

        #remove illegal characters
        edi_doc = edi_doc.replace('ä', 'a').replace('Ä', 'A').replace('ö', 'o').replace('Ö', 'O').replace('ü', 'u').replace('Ü', 'U').replace('ß', 's').replace('ç', 'c').replace('Ç', 'C').replace('â', 'a').replace('Ğ', 'G').replace('ğ', 'g').replace('İ', 'I').replace('î', 'i').replace('Ş', 'S').replace('ş', 's').replace('´', ' ')
        
        # Return the result
        return edi_doc


    #Import section
    @api.model
    def edi_import_calwms_validator(self, document_ids):
        _logger.info("Validating CALwms document")
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
        extra_lines = ''

        for lin in content.splitlines():
            if i == 0:
                ZNPREF = lin[30:64].strip()
                break

        delivery = self.search([('name', '=', ZNPREF)])
        _logger.debug("Delivery found %d (%s)", delivery.id, delivery.name)
        Lot = self.env['stock.production.lot']
        Quant = self.env['stock.quant']

        #processed_ids = []
        if delivery.state == 'done':
            _logger.debug("Delivery %s in status Done, skipping processing")
        
        else:
            for edi_line in content.splitlines():
                # map line to relevant fields
                if i == 0:
                    i += 1
                    continue

                if i > 0:
                    ZRTYPE = edi_line[31:34].strip() #001 for Inbound, 011 for outbound
                    ZRZRPR = edi_line[34:68].strip() #Line Reference
                    ZRARID = edi_line[72:85].strip() #Item Code
                    ZRPTID = edi_line[86:120].strip() #Lot Number
                    ZRVVDT = edi_line[144:152].strip() #Minimal BBD
                    ZRPHAN = edi_line[290:295].strip() #QTY Delivered in SKU
                    BBD = ZRVVDT[0:4]+'-'+ZRVVDT[4:6]+'-'+ZRVVDT[6:8]
                    AssignLot = False
                    
                    #to implement: if EDI Document contains lines that don't match edi_sequence on picking 
                    # >> log line to chatter and move to next EDI line.
                    #move_line = delivery.move_lines.filtered(lambda ml: str(int(ml.edi_sequence)) == str(int(ZRZRPR)))
                    move_line = delivery.move_lines.filtered(lambda ml: ml.edi_sequence == ZRZRPR.rjust(6).replace(' ','0'))
                
                    if not move_line:
                        if extra_lines == '':
                            extra_lines += 'No stock move for products: '
                        extra_lines += ZRARID+' '
                    else:
                        #check for move line ids, if they do not exist, try to create
                        if len(move_line.move_line_ids) == 0:
                            #move_line.quantity_done = float(ZRPHAN)
                            move_line._action_confirm()
                            move_line._action_assign()
                            _logger.info("No Pack Operation found for EDI Sequence %s, Product %s... creating", ZRZRPR, ZRARID)
                        
                        #if the quantity done = 0, there will not be a move_line_id.
                        if len(move_line.move_line_ids) > 0:
                             
                            #remove existing reservations
                            #move_line.move_line_ids[0].product_uom_qty = 0.0
                            #move_line.move_line_ids[0].lot_id = ''
                            #move_line.move_line_ids[0]._free_reservation(move_line.product_id, move_line.location_id, 0.0)
                            #move_line.move_line_ids[0].write({
                            #    'product_uom_qty': 0.0,
                            #    'lot_id': '',
                            #})

                            ml = move_line.move_line_ids[0]
                            Quant._update_reserved_quantity(ml.product_id, ml.location_id, 0.0, lot_id=ml.lot_id, package_id=ml.package_id, owner_id=ml.owner_id, strict=True)

                            if not move_line.move_line_ids[0].lot_id:
                                #force lot assignment
                                _logger.debug('No Lot Was Assigned to move_line, Assigning')
                                AssignLot = True
                        
                            if ZRTYPE == '001' or AssignLot: #Inbound Only, or when creating a new move_line_id
                                CurrentLots = Lot.search([('name', '=', str(ZRPTID))])
                                Match = 0
                                for CurrentLot in CurrentLots:
                                    if CurrentLot.product_id == move_line.product_id and CurrentLot.name == str(ZRPTID) and Match == 0:
                                        _logger.debug('Existing lot %s for product! %s', CurrentLot.name, ZRARID)
                                        Match = 1
                                        try:
                                            move_line.move_line_ids[0].lot_id = CurrentLot
                                        except:
                                            body = ("Not enough stock for: ", ZRARID)
                                            document.message_post(body)
                                        move_line.qty_done = float(ZRPHAN)
                                        move_line._quantity_done_set()
                                            
                                if Match == 0:
                                    move_line.move_line_ids[0].lot_id = Lot.create({'name': str(ZRPTID),'product_id': move_line.product_id.id})
                                    _logger.debug('No matching lot, created lot for %s', ZRPHAN)
                                    if ZRVVDT:
                                        move_line.move_line_ids[0].lot_id.use_date = BBD
                                    else:
                                        _logger.info("No Best Before Date")
                                        pass
                                move_line.move_line_ids[0].qty_done = float(ZRPHAN)
                                _logger.info("move_line %d prepared with content: lot %s quantity %d bestbefore %s", int(ZRZRPR), ZRPTID, float(ZRPHAN), str(BBD))
                            else:
                                move_line.move_line_ids[0].qty_done = float(ZRPHAN)
                                _logger.info("move_line %d prepared with content: product %s quantity %s",int(ZRZRPR),ZRARID,str(ZRPHAN))
                    
            #log extra lines from EDI doc
            if extra_lines != '':
                _logger.info("Extra Lines: %s", extra_lines)
                #body = (_("Extra Lines: %s", extra_lines))
                body = ("Extra lines in EDI", extra_lines)
                delivery.message_post(body)
            
            # execute the transfer of the picking
            delivery.action_done()
            backorder = self.search([('backorder_id', '=', delivery.id)])
            if backorder:
                backorder.action_cancel()
                _logger.info("Backorder %s Cancelled.", str(backorder.name))
       
        return True
