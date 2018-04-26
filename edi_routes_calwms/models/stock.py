import datetime
import logging
from odoo import api, _
from odoo import models, fields
from odoo.exceptions import except_orm
from odoo.addons.edi_tools.models.edi_mixing import EDIMixin

_logger = logging.getLogger(__name__)

class stock_picking(models.Model, EDIMixin):
    _inherit = "stock.picking"

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
        #edi_doc = []
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
            ZRADID = str(delivery.partner_id.id)
            ZRZRRG = str(line_counter)
            ZRTYPE = ZNTYPE
            ZRARID = str(product.barcode)
            ZRAVEO = str(int(line.product_uom_qty))

            line_counter = line_counter + 1
            line_content = ZRRECT.ljust(3) + ZRVERS.ljust(1) + ZRADID.ljust(14) + ''.ljust(3) + ZRZRRG.ljust(3) + ZRTYPE.ljust(3) + ''.ljust(38) + ZRARID.ljust(14) + ''.ljust(169) + ZRAVEO.ljust(6)
            edi_doc = edi_doc +line_content + '\n'

        # Return the result
        return edi_doc
