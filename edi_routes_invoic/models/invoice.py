import copy
import datetime
import logging


from odoo import api, _, models
from odoo.exceptions import UserError
from odoo.addons.edi_tools.models.edi_mixing import EDIMixin
from odoo.addons.edi_tools.models.exceptions import EdiValidationError
LOGGER = logging.getLogger(__name__)

LINE = {
    'ARTIKEL': '',  # account.invoice.line:product_id -> product.product:ean13
    'ARTIKELREF': '',  # account.invoice.line:product_id -> product.product:name
    'ARTIKELOMSCHRIJVING': '',  # account.invoice.line:product_id -> product.product:sale_description
    'AANTAL': '',  # account.invoice.line:quantity
    'AANTALGELEVERD': '',  # account.invoice.line:quantity
    'LIJNTOTAAL': 0,  # account.invoice.line:price_subtotal
    'UNITPRIJS': 0,  # account.invoice.line:price_unit
    'BTWPERCENTAGE': 0,  # account.invoice.line.vat (met naam VAT*) account.tax:amount * 100
    'LIJNTOTAALBELAST': 0,  # account.invoice.line:price_subtotal
    'BEBAT': 0,  # account.invoice.line:vat (alle VAT's met naam "Bebat") som van account.tax:amount
    'BEBATLIJN': 0,  # account.invoice.line:quantity * BEBAT (zie vorige lijn)
    'RECUPEL': 0,  # account.invoice.line:vat (alle VAT's met naam "Recupel") som van account.tax:amount
    'RECUPELLIJN': 0,  # account.invoice.line:quantity * RECUPEL (zie vorige lijn)
}

INVOICE = {
    'FACTUURNUMMER': '',  # account.invoice:number
    'FACTUURNAAM': '',
    'ORDERNAAM':'',
    'ORDERSTRAAT': '',  # order.partner_id.street
    'ORDERSTRAAT2' : '', # order.partner_id.street2
    'ORDERPOSTCODE': '',  # order.partner_id.zip
    'ORDERSTAD': '',  # order.partner_id.city
    'DATUM': '',  # account.invoice:create_date
    'FACTUURDATUM': '',  # account.invoice:date_invoice
    'VERVALDATUM': '',  # account.invoice:date_due
    'LEVERDATUM': '',  # account.invoice:origin -> stock.picking.out:date_done
    'KLANTREFERENTIE': '',  # account.invoice:name
    'REFERENTIEDATUM': '',  # account.invoice:origin -> sale.order:date_order
    'LEVERINGSBON': '',  # account.invoice:origin -> stock.picking.out:name
    'LEVERPLANDATUM': '',  # account.invoice:origin -> stock.picking.out:scheduled_date
    'AANKOPER': '',  # account.invoice:origin -> sale.order:partner_id -> res.partner:ref
    'LEVERANCIER': '',  # res.company:partner_id -> res.partner:ref  (er is normaal maar 1 company)
    'BTWLEVERANCIER': '',  # res.company:partner_id -> res.partner:vat  (er is normaal maar 1 company)
    'LEVERPLAATS': '',  # account.invoice:origin -> stock.picking.out:partner_id -> res.partner:ref
    'FACTUURPLAATS': '',  # account.invoice:partner_id -> res.partner:ref
    'BTWFACTUUR': '',  # account.invoice:partner_id -> res.partner:vat
    'VALUTA': 'EUR',
    'LIJNEN': [],
    'FACTUURPERCENTAGE': 0,
    'FACTUURTOTAAL': 0,  # account.invoice:amount_total
    'FACTUURMVH': 0,  # account.invoice:amount_untaxed
    'FACTUURSUBTOTAAL': 0,  # account.invoice:amount_untaxed
    'TOTAALBTW': 0,  # account.invoice:amount_untaxed * 1,21 - amount_untaxed
    'BEBATTOTAAL': 0,  # som van alle line items: BEBATLIJN
    'RECUPELTOTAAL': 0,  # som van alle line items: RECUPELLIJN
    'KOSTENTOTAAL': 0,  # som van alle service product kosten (bv transport)
}


class account_invoice(models.Model, EDIMixin):
    _name = "account.invoice"
    _inherit = "account.invoice"

    @api.model
    def valid_for_edi_export_invoic(self, record):
        if record.state != 'open':
            return False
        return True

    
    def send_edi_export_invoic(self, partner_id):
        valid_invoices = self.filtered(self.valid_for_edi_export_invoic)
        invalid_invoices = [p for p in self if p not in valid_invoices]
        if invalid_invoices:
            raise UserError(_('The following pickings are invalid, please remove from selection. %s') % (map(lambda record: record.name, invalid_invoices)))

        for invoice in valid_invoices:
            content = invoice.edi_export_invoic(invoice, None)
            result = self.env['edi.tools.edi.document.outgoing'].create_from_content(invoice.number, content, partner_id.id, 'account.invoice', 'send_edi_export_invoic', type='json')
            if not result:
                raise UserError(_('EDI processing failed for the following invoice %s') % (invoice.number))

        return True

    def edi_export_invoic(self, invoice, edi_struct=None, context=None):
        # Instantiate variables
        edi_doc = copy.deepcopy(dict(INVOICE))

        # ref = invoice.origin.partition(':')
        pick_db = self.env['stock.picking']
        order_db = self.env['sale.order']
        partner_db = self.env['res.partner']
        tax_db = self.env['account.tax']
        product_db = self.env['product.product']
        company_db = self.env['res.company']

        delivery = pick_db.search([('origin', '=', invoice.origin)])
        if not delivery:
            raise UserError(_("Could not find delivery for invoice: {!s}").format(invoice.number))
        order = order_db.search([('name', '=', invoice.origin)])
        if not order:
            raise UserError(_("Could not find order for invoice: {!s}").format(invoice.number))
        company = company_db.search([])[0]

        now = datetime.datetime.now()

        # Basic header fields
        # -------------------
        edi_doc['FACTUURNUMMER'] = invoice.number
        edi_doc['DATUM'] = now.strftime("%Y%m%d")
        edi_doc['FACTUURDATUM'] = invoice.date_invoice.strftime("%Y%m%d")
        edi_doc['VERVALDATUM'] = invoice.date_due.strftime("%Y%m%d")
        edi_doc['KLANTREFERENTIE'] = invoice.name[:17]
        edi_doc['FACTUURTOTAAL'] = invoice.amount_total
        edi_doc['FACTUURSUBTOTAAL'] = invoice.amount_untaxed

        # edi_doc['TOTAALBTW'] = float('%.2f' % ((invoice.amount_untaxed + edi_doc['BEBATTOTAAL'] + edi_doc['RECUPELTOTAAL'])

        partner = partner_db.browse(invoice.partner_id.id, context)
        if partner:
            edi_doc['FACTUURPLAATS'] = partner.ref
            edi_doc['BTWFACTUUR'] = partner.vat
            edi_doc['ORDERPLAATS'] = order.partner_id.ref
            edi_doc['ORDERNAAM'] = order.partner_id.name[:35].upper()
            edi_doc['ORDERSTRAAT'] = order.partner_id.street[:35].upper()
            if invoice.partner_id.street2:
                edi_doc['ORDERSTRAAT2'] = invoice.partner_id.street2[:35].upper()
            edi_doc['ORDERPOSTCODE'] = order.partner_id.zip
            edi_doc['ORDERSTAD'] = order.partner_id.city
            edi_doc['FACTUURNAAM'] = invoice.partner_id.name[:35]
        if company:
            partner = partner_db.browse(company.partner_id.id, context)
            if partner:
                edi_doc['LEVERANCIER'] = partner.ref
                edi_doc['BTWLEVERANCIER'] = partner.vat
                edi_doc['ORDERPLAATS'] = order.partner_id.ref
                edi_doc['ORDERNAAM'] = order.partner_id.name[:35].upper()
                edi_doc['ORDERSTRAAT'] = order.partner_id.street[:35].upper()
                if invoice.partner_id.street2:
                    edi_doc['ORDERSTRAAT2'] = invoice.partner_id.street2[:35].upper()
                edi_doc['ORDERPOSTCODE'] = order.partner_id.zip
                edi_doc['ORDERSTAD'] = order.partner_id.city
                edi_doc['FACTUURNAAM'] = invoice.partner_id.name[:35]

        # Delivery order fields
        edi_doc['LEVERDATUM'] = delivery.date_done.strftime("%Y%m%d")
        if delivery.desadv_name:
            edi_doc['LEVERINGSBON'] = delivery.desadv_name
        else:
            edi_doc['LEVERINGSBON'] = delivery.name

        edi_doc['LEVERPLANDATUM'] = delivery.scheduled_date.strftime("%Y%m%d")
        partner = partner_db.browse(delivery.partner_id.id, context)
        if partner:
            edi_doc['LEVERPLAATS'] = partner.ref

        # Sale order fields
        edi_doc['REFERENTIEDATUM'] = order.date_order.strftime("%Y%m%d")
        partner = partner_db.browse(order.partner_id.id, context)
        if partner:
            edi_doc['AANKOPER'] = partner.ref

        # Line items
        for line in invoice.invoice_line_ids:
            product = product_db.browse(line.product_id.id, context)

            if product.type and product.type == 'service':  # product type used to indicate extra costs
                edi_doc['KOSTENTOTAAL'] += line.price_subtotal
                continue

            edi_line = copy.deepcopy(dict(LINE))
            edi_line['ARTIKEL'] = product.barcode
            edi_line['ARTIKELREF'] = product.name
            edi_line['ARTIKELOMSCHRIJVING'] = product.description_sale[:35].upper() if product.description_sale else ''
            edi_line['AANTAL'] = line.quantity
            edi_line['AANTALGELEVERD'] = line.quantity
            edi_line['LIJNTOTAAL'] = line.price_subtotal

            edi_line['UNITPRIJS'] = line.price_unit
            edi_line['LIJNTOTAALBELAST'] = line.price_subtotal

            for line_tax in line.invoice_line_tax_ids:
                vat = tax_db.browse(line_tax.id, context)
                if "Bebat" in vat.name:
                    edi_line['BEBAT'] += vat.amount
                elif "Recupel" in vat.name:
                    edi_line['RECUPEL'] += vat.amount
                elif "VAT" in vat.name:
                    edi_line['BTWPERCENTAGE'] = int(vat.amount * 100)
                    edi_doc['FACTUURPERCENTAGE'] = edi_line['BTWPERCENTAGE']

            if edi_line['BEBAT'] != True:
                edi_line['BEBATLIJN'] = edi_line['BEBAT'] * line.quantity
            else:
                edi_line['BEBATLIJN'] = 0
            if edi_line['RECUPEL'] != True:
                edi_line['RECUPELLIJN'] = edi_line['RECUPEL'] * line.quantity
            else:
                edi_line['RECUPELLIJN'] = 0

            edi_doc['LIJNEN'].append(edi_line)

        # Final BEBAT & RECUPEL calculations
        for line in edi_doc['LIJNEN']:
            edi_doc['BEBATTOTAAL'] += line['BEBATLIJN']
            edi_doc['RECUPELTOTAAL'] += line['RECUPELLIJN']

        # Final tax calculation
        edi_doc['TOTAALBTW'] = float('%.2f' % ((invoice.amount_untaxed + edi_doc['BEBATTOTAAL'] + edi_doc['RECUPELTOTAAL']) * edi_doc['FACTUURPERCENTAGE'] / 100))
        edi_doc['FACTUURMVH'] = invoice.amount_untaxed + edi_doc['BEBATTOTAAL'] + edi_doc['RECUPELTOTAAL']

        # Return the result
        return edi_doc
