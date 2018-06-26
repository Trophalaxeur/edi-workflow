#import copy
import logging
import datetime
import pytz
#import json

from odoo import api, _
from odoo import models, fields
from odoo.exceptions import except_orm
from odoo.addons.edi_tools.models.edi_mixing import EDIMixin

_logger = logging.getLogger(__name__)

class account_invoice(models.Model, EDIMixin):
    _name = "account.invoice"
    _inherit = "account.invoice"

    partner_sent = fields.Datetime(string='Partner Sent')

    @api.model
    def valid_for_edi_export_invoice_targo(self, record):
        if record.state != 'open':
            return True
        return True

    @api.multi
    def send_edi_export_invoice_targo(self, partner_id):
        valid_invoices = self.filtered(self.valid_for_edi_export_invoice_targo)
        invalid_invoices = [p for p in self if p not in valid_invoices]
        if invalid_invoices:
            raise except_orm(_('Invalid pickings in selection!'), _('The following pickings are invalid, please remove from selection. %s') % (map(lambda record: record.name, invalid_invoices)))

        content = valid_invoices.edi_export_invoice_targo(edi_struct=None)
        result = self.env['edi.tools.edi.document.outgoing'].create_from_content('targo', content, partner_id.id, 'account.invoice', 'send_edi_export_invoice_targo', type='STRING')
        if not result:
            raise except_orm(_('EDI creation failed!', _('EDI processing failed for the following invoice %s') % (invoice.name)))

        return result

    @api.multi
    def edi_export_invoice_targo(self, edi_struct=None):
        inv_db = self.pool.get('account.invoice')
        edi_doc = ''
        grand_total = 0.0
        invoice_counter = 0
        corp = '1   '
        for invoice in self:
            #field definition
            label = '10'
            corp = '1   ' #1 = TARGO Commercial Finance, 4 = TARGO Factoring
            client = '12578'
            if invoice.partner_id.parent_id:
                debtor = str(invoice.partner_id.parent_id.targo_reference).ljust(10)
            else:
                debtor = str(invoice.partner_id.targo_reference).ljust(10)
            debtor_type = '2'
            invoice_name = str(invoice.number)[-10:].ljust(10)
            invoice_date = datetime.datetime.strptime(invoice.date_invoice, "%Y-%m-%d").strftime("%d%m%Y")
            value_date = datetime.datetime.strptime(invoice.date_invoice, "%Y-%m-%d").strftime("%d%m%Y")
            amount_total = str(('%.2f' % invoice.amount_total).replace('.',',')).rjust(14)
            if invoice.type == 'out_invoice':
                invoice_type = '+' #+ for invoices, - for credit notes 
                grand_total += invoice.amount_total
            else:
                invoice_type = '-'
                grand_total -= invoice.amount_total
            amount_tax = str(('%.2f' % invoice.amount_tax).replace('.',',')).rjust(14)
            currency = invoice.currency_id.name
            termcode = ''.ljust(3)
            if invoice.payment_term_id:
                termdays = str(invoice.payment_term_id.line_ids[0].days).ljust(3)
                if invoice.payment_term_id.line_ids[0].option == 'day_after_invoice_date':
                    endofmonth = '0'
                else:
                    endofmonth = '1'
            else:
                termdays = str("28").ljust(3)
                endofmonth = '1'
            maturity_date = datetime.datetime.strptime(invoice.date_due, "%Y-%m-%d").strftime("%d%m%Y")
            discount_1_days = str(invoice.partner_id.discount_1_days).ljust(3)
            discount_2_days = str(invoice.partner_id.discount_2_days).ljust(3)
            discount_3_days = str(invoice.partner_id.discount_3_days).ljust(3)
            discount_1_perc = str(invoice.partner_id.discount_1_perc).ljust(7)
            discount_2_perc = str(invoice.partner_id.discount_2_perc).ljust(7)
            discount_3_perc = str(invoice.partner_id.discount_3_perc).ljust(7)
            endofmonthdays = '   '
            transfer_days = '   '
            dname = invoice.partner_id.name[:30].ljust(40)
            dstreet = invoice.partner_id.street[:30].ljust(40)
            dzip = invoice.partner_id.zip[:10].ljust(10)
            dcity = invoice.partner_id.city[:35].ljust(40)
            dcountry = invoice.partner_id.country_id.code.ljust(2)
            finremark = '   '
            submitter = ''.ljust(5)

            #append lines
            line_content = label + corp + client + debtor + debtor_type + invoice_name + invoice_date + value_date + amount_total + invoice_type + amount_tax +currency + termcode + termdays + maturity_date + discount_1_perc + discount_1_days + discount_2_perc + discount_2_days + discount_3_perc + discount_3_days + endofmonth + endofmonthdays + transfer_days + dname + dstreet + dzip + dcity + dcountry + finremark + submitter
            edi_doc = edi_doc +line_content + '\n'
            invoice_counter += 1

            #set edi_partner_sent
            invoice.partner_sent = pytz.utc.localize(datetime.datetime.utcnow())
        
        #append final line
        label = '30'
        grand_total = str(grand_total).replace('.',',')
        footer = label + corp + client + ''.ljust(11) + str(invoice_counter).ljust(26) + grand_total.ljust(218) + submitter
        edi_doc = edi_doc + footer + '\n'

        #remove illegal characters
        edi_doc = edi_doc.replace('ä', 'a').replace('Ä', 'A').replace('ö', 'o').replace('Ö', 'O').replace('ü', 'u').replace('Ü', 'U').replace('ß', 's').replace('ç', 'c').replace('Ç', 'C').replace('â', 'a').replace('Ğ', 'G').replace('ğ', 'g').replace('İ', 'I').replace('î', 'i').replace('Ş', 'S').replace('ş', 's')
        
        #return consolidated result
        return edi_doc
