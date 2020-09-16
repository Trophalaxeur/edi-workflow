import csv
from itertools import groupby
import logging
import StringIO

from odoo import api, _, models
from openerp.osv import osv
from odoo.addons.edi_tools.models.exceptions import EdiValidationError

_logger = logging.getLogger(__name__)


class stock_picking(models.Model):
    _inherit = "stock.picking"

    @api.model
    def edi_import_essers_pclo_validator(self, document_ids):
        ORDER_NUMBER = 'Ordernummer EDI'
        ORDER_LINE_NUMBER = 'ORIGINAL'

        move_db = self.env['stock.move']
        edi_db = self.env['edi.tools.edi.document.incoming']

        document = edi_db.browse(document_ids)
        document.ensure_one()

        content = self.cleanup_pclo_file(document.content)
        reader = csv.DictReader(content, delimiter=';', quotechar='"', skipinitialspace=True)

        sorted_rows = sorted(reader, key=lambda row: (row[ORDER_NUMBER], row[ORDER_LINE_NUMBER]))
        for delivery_number, rws in groupby(sorted_rows, lambda row: row[ORDER_NUMBER]):
            rows = list(rws)
            delivery = self.env['stock.picking'].search([('name', '=', delivery_number.replace('_', '/'))], limit=1)

            if not delivery:
                raise EdiValidationError("Delivery %s doesn't exist" % (delivery_number.replace('_', '/')))

            #moves_not_assigned = delivery.move_lines.filtered(lambda ml: ml.state != 'assigned')
            #if moves_not_assigned:
            #    raise EdiValidationError("Move lines present in delivery %s which don't have status assigned" % (delivery.name))

            no_matching_move_line_for_edi_sequence = []
            for row in rows:
                move = delivery.move_lines.filtered(lambda ml: ml.edi_sequence == row[ORDER_LINE_NUMBER])
                if not move:
                    no_matching_move_line_for_edi_sequence.append(row[ORDER_LINE_NUMBER])

            if no_matching_move_line_for_edi_sequence:
                raise EdiValidationError("No move lines are found for following edi_sequences in delivery %s.<br/>%s" % (delivery.name, "<br/>".join(no_matching_move_line_for_edi_sequence)))
        _logger.info('pclo validator: no errors') 
        return True

    @api.cr_uid_context
    def receive_edi_import_essers_pclo(self, cr, uid, ids, context=None):
        edi_db = self.pool.get('edi.tools.edi.document.incoming')
        document = edi_db.browse(cr, uid, ids, context)  # edi doc

        content = self.cleanup_pclo_file(document.content)
        self.edi_import_essers_pclo(cr, uid, content, context=context)

        return True

    def cleanup_pclo_file(self, dirty_content):
        '''Handle the weird format of Essers "CSV" files. Return list of lines that resemble an actual CSV format.
           1: PCLOREPORT
           2: headers
           3:
           4:
           5: first line csv'''
        content = dirty_content.replace('="', '"').split("\n")
        content = map(lambda row: row.strip(), content)
        if len(content) > 4:  # there has to be at least 5 lines to be able to do something
            header = content[1]  # get the header on line 2
            body = content[4:]  # skip line 3 and 4 and get the remaining content
            content = [header] + body

        _logger.info('cleanup_pclo_file success')
        return content

    def edi_import_essers_pclo(self, cr, uid, pclofile, context=None):
        pick_db = self.pool.get('stock.picking')
        move_db = self.pool.get('stock.move')
        pack_db = self.pool.get('stock.quant.package')
        operation_db = self.pool.get('stock.pack.operation')
        ul_db = self.pool.get('product.ul')

        PALLET_NUMBER = 'Palletnumber'
        PALLET_TYPE = 'Pallet size'
        PALLET_WEIGHT_BRUT = 'TOTPALBRUTO'
        PALLET_WEIGHT_NET = 'Tot.Pal.'
        BOX_TYPE = 'Doostype'
        COLLI_NUMBER = 'Product extension 4'
        COLLI_WEIGHT_BRUT = 'TOTCOLBRUTO'
        COLLI_WEIGHT_NET = 'TOTCOLNETT'
        ORDER_NUMBER = 'Ordernummer EDI'
        ORDER_LINE_NUMBER = 'ORIGINAL'
        ORDER_LINE_PARENT = 'ORIGINAL PARENT'
        ORDER_LINE_QUANTITY = 'Quan Pallet'

        def ref(module, xml_id):
            proxy = self.pool.get('ir.model.data')
            return proxy.get_object_reference(cr, uid, module, xml_id)

        reader = csv.DictReader(pclofile, delimiter=';', quotechar='"', skipinitialspace=True)
        note = []
        sscc_dictionary = {}
        sorted_rows_by_pallet_box = sorted(reader, key=lambda row: (row[PALLET_NUMBER], row[COLLI_NUMBER]))
        for pallet, rows in groupby(sorted_rows_by_pallet_box, lambda row: row[PALLET_NUMBER]):
            pallet_initialized = False

            for row in rows:
                # get pallet information from first row
                if not pallet_initialized and pallet:
                    # create tracking obj for the pallet if necessary
                    package_ids = pack_db.search(cr, uid, [('name', '=', pallet)])
                    if package_ids:
                        pallet_package_id = package_ids[0]
                    else:
                        if row[PALLET_TYPE] == 'EUR':
                            ul_model, ul_id = ref('edi_routes_essers_pclo', 'product_ul_euro_pallet')
                        elif row[PALLET_TYPE] == 'DD':
                            ul_model, ul_id = ref('edi_routes_essers_pclo', 'product_ul_half_pallet')
                        elif row[PALLET_TYPE] == 'WWP':
                            ul_model, ul_id = ref('edi_routes_essers_pclo', 'product_ul_disposable_pallet')
                        else:
                            ul_model, ul_id = ref('edi_routes_essers_pclo', 'product_ul_essers_pallet')
                    
                        weight = row[PALLET_WEIGHT_BRUT]
                        weight_net = row[PALLET_WEIGHT_NET]

                        pallet_package_id = pack_db.create(cr, uid, {
                            'name': pallet,
                            'ul_id': ul_id,
                            'weight': weight,
                            'weight_net': weight_net
                        })
                    pallet_initialized = True

                # products directly on pallet, no need to create box
                if not row[COLLI_NUMBER]:
                    sscc_dictionary[pallet] = pallet_package_id
                    continue

                # create tracking obj for the boxes if necessary
                box = row[COLLI_NUMBER]
                
                if row[BOX_TYPE] == 'BLA':
                    ul_model, ul_id = ref('edi_routes_essers_pclo', 'product_ul_bla_box')
                elif row[BOX_TYPE] == 'BSM':
                    ul_model, ul_id = ref('edi_routes_essers_pclo', 'product_ul_bsm_box')
                elif row[BOX_TYPE] == 'BME':
                    ul_model, ul_id = ref('edi_routes_essers_pclo', 'product_ul_bme_box')
                else:
                    ul_model, ul_id = ref('edi_routes_essers_pclo', 'product_ul_essers_box')
                
                weight = row[COLLI_WEIGHT_BRUT]
                weight_net = row[COLLI_WEIGHT_NET]

                package_ids = pack_db.search(cr, uid, [('name', '=', box)])
                if package_ids:
                    box_tracking_id = package_ids[0]
                else:
                    vals = {
                        'name': box,
                        'ul_id': ul_id,
                        'weight': weight,
                        'weight_net': weight_net
                    }
                    if pallet:
                        vals['parent_id'] = pallet_package_id  # product in box, box not on pallet
                    box_tracking_id = pack_db.create(cr, uid, vals)

                sscc_dictionary[box] = box_tracking_id

        reader = csv.DictReader(pclofile, delimiter=';', quotechar='"', skipinitialspace=True)
        sorted_rows = sorted(reader, key=lambda row: (row[ORDER_NUMBER], row[ORDER_LINE_NUMBER]))
        for delivery_number, rws in groupby(sorted_rows, lambda row: row[ORDER_NUMBER]):
            rows = list(rws)
            delivery_ids = pick_db.search(cr, uid, [('name', '=', delivery_number.replace('_', '/'))])
            if not delivery_ids:
                continue
            delivery = pick_db.browse(cr, uid, delivery_ids)[0]

            if delivery.state == 'done':
                _logger.info('Delivery already in state \'done\'. Skip processing.')
                continue

            if not delivery.pack_operation_ids:
                _logger.info('No Pack Operation IDS. do_prepare partial processing.')
                delivery.do_prepare_partial()

            processed_ids = []
            for move in delivery.move_lines:
                _logger.info('processing move_line: %s.', move)
                if move.state == 'done':
                    _logger.info('move done, skipping: %s.', move)
                    continue
                rows_for_sequence = [r for r in rows if r[ORDER_LINE_NUMBER] == move.edi_sequence]
                if move.linked_move_operation_ids:
                    ref_operation = move.linked_move_operation_ids[0].operation_id # normally there should only be one operation per move
                if rows_for_sequence:
                    for row in rows_for_sequence:
                        quantity = float(row[ORDER_LINE_QUANTITY]) or 0.0
                        sscc_code = row[COLLI_NUMBER] or row[PALLET_NUMBER]
                        op = operation_db.copy(cr, uid, ref_operation.id, {'product_qty': quantity ,'qty_done': quantity, 'result_package_id': sscc_dictionary[sscc_code]})
                        processed_ids.append(op)
                    _logger.info('rows for sequence: %s.', rows_for_sequence)
            _logger.info('processed_ids: %s.', processed_ids) 
            unprocessed_ids = operation_db.search(cr, uid, ['&', ('picking_id', '=', delivery.id), '!', ('id', 'in', processed_ids)])
            _logger.info('unprocessed_ids: %s.', unprocessed_ids)
            operation_db.unlink(cr, uid, unprocessed_ids)
            delivery.do_transfer()
