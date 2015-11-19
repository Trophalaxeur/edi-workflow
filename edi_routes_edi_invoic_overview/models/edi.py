from datetime import datetime
import json

from openerp import models, api, _
from openerp.tools.misc import DEFAULT_SERVER_DATE_FORMAT
from openerp.exceptions import except_orm


class EdiToolsEdiDocumentOutgoing(models.Model):
    _inherit = "edi.tools.edi.document.outgoing"

    @api.model
    def valid_for_edi_export_edi_invoic_overview(self, record):
        return (record.flow_id.name == 'INVOIC D96A(out)' and record.flow_id.model == 'account.invoice')

    @api.multi
    def send_edi_export_edi_invoic_overview(self, partner_id):
        valid_edi_documents = self.filtered(self.valid_for_edi_export_edi_invoic_overview)
        invalid_edi_documents = [p for p in self if p not in valid_edi_documents]
        if invalid_edi_documents:
            raise except_orm(_('Invalid EDI documents in selection!'), _('The following EDI documents are invalid, please remove from selection. %s') % (map(lambda record: record.name, invalid_edi_documents)))

        content = self.edi_export_edi_invoic_overview()
        document_name = "%s-%s" % (partner_id.name, datetime.strftime(datetime.utcnow(), DEFAULT_SERVER_DATE_FORMAT))
        self.env['edi.tools.edi.document.outgoing'].create_from_content(document_name, content, partner_id.id, 'edi.tools.edi.document.outgoing', 'send_edi_export_edi_invoic_overview', type='STRING')

        return True

    @api.multi
    def edi_export_edi_invoic_overview(self):
        result = '<html>\n<table width="100%">\n'
        # companydetails
        company = self.env['res.company'].search([('id','=',1)])
        result += '<tr>\n'
        result += '<td colspan="2" valign="top">Afzender:</td>\n<td colspan="2" valign="top">'
        if company.name: result += company.name + '<br/>\n'
        if company.street: result += company.street + '<br/>\n'
        if company.street2: result += company.street2 + '<br/>\n'
        if company.zip: result += company.zip + ' '
        if company.city: result += company.city
        if company.vat: result += '<br/>\n' + company.vat
        result += '</td>\n'

        # partnerdetails
        for partners in self:
            partner = partners.partner_id

        result += '<td colspan="2" valign="top">Bestemmeling:</td><td colspan="2" valign="top">\n'
        if partner.name: result += partner.name + '<br/>\n'
        if partner.street: result += partner.street + '<br/>\n'
        if partner.street2: result += partner.street2 + '<br/>\n'
        if partner.zip: result += partner.zip + ' '
        if partner.city: result += partner.city
        if partner.vat: result += '<br/>\n' + partner.vat
        result += '</td></tr>\n'
        result += '<tr><td>&nbsp;</td></tr>\n'

        # Sending details
        now = datetime.now()
        result += '<tr><td colspan="3">Verzendingsdatum: ' + now.strftime("%d/%m/%Y") + '</td>\n'
        overview = "%s-%s" % (partner.name, datetime.strftime(datetime.utcnow(), DEFAULT_SERVER_DATE_FORMAT))
        result += '<td colspan="3">Interchange: ' + overview + '</td></tr>\n'
        result += '<tr><td>&nbsp;</td></tr>\n'

        # Headers
        result += '<tr>'
        result += '<td><strong>Nr factuur:</strong></td>\n'
        result += '<td><strong>Datum factuur:</strong></td>\n'
        result += '<td><strong>Nr bestelling:</strong></td>\n'
        result += '<td align="right"><strong>Bedrag excl. BTW:</strong></td>\n'
        result += '<td align="right"><strong>BTW:</strong></td>\n'
        result += '<td align="right"><strong>Bedrag incl. BTW:</strong></td>\n'
        result += '</tr>\n'

        # Content
        tot_excl = 0
        btw = 0
        tot_incl = 0
        for document in self:
            result += '<tr>\n'
            content = json.loads(document.content)
            result += '<td>' + content['FACTUURNUMMER'] + '</td>\n'
            result += '<td>' + content['FACTUURDATUM'] + '</td>\n'
            result += '<td>' + content['KLANTREFERENTIE'] + '</td>\n'
            result += '<td align="right">' + str(content['FACTUURMVH']) + '</td>\n'
            result += '<td align="right">' + str(content['TOTAALBTW']) + '</td>\n'
            result += '<td align="right">' + str(content['FACTUURTOTAAL']) + '</td>\n'
            result += '</tr>\n'

            tot_excl += content['FACTUURMVH']
            btw += content['TOTAALBTW']
            tot_incl += content['FACTUURTOTAAL']

        # Total footer
        result += '<tr><td>&nbsp;</td></tr>\n'
        result += '<tr>\n'
        result += '<td colspan="3">Totaal ' + str(len(self)) + ' facturen</td>\n'
        result += '<td align="right">' + str(tot_excl) + '</td>\n'
        result += '<td align="right">' + str(btw) + '</td>\n'
        result += '<td align="right">' + str(tot_incl) + '</td>\n'
        result += '</tr>'

        # BTW footer
        result += '<tr><td>&nbsp;</td></tr>\n'
        result += '<tr><td colspan="6"><strong>Per BTW tarief</strong></td></tr>\n'

        result += '<tr>\n'
        result += '<td colspan="3">BTW 06.00 %</td>\n'
        result += '<td align="right">0.00</td>\n'
        result += '<td align="right">0.00</td>\n'
        result += '<td align="right">0.00</td>\n'
        result += '</tr>\n'

        result += '<tr>\n'
        result += '<td colspan="3">BTW 12.00 %</td>\n'
        result += '<td align="right">0.00</td>\n'
        result += '<td align="right">0.00</td>\n'
        result += '<td align="right">0.00</td>\n'
        result += '</tr>\n'

        result += '<tr>\n'
        result += '<td colspan="3">BTW 21.00 %</td>\n'
        result += '<td align="right">' + str(tot_excl) + '</td>\n'
        result += '<td align="right">' + str(btw) + '</td>\n'
        result += '<td align="right">' + str(tot_incl) + '</td>\n'
        result += '</tr>\n'

        result += '</table></html>\n'
        return result

    @api.model
    def run_send_edi_export_edi_invoic_overview(self):
        flow = self.env['edi.tools.edi.flow'].search([('model', '=', 'edi.tools.edi.document.outgoing'), ('name', '=', 'Invoice Overview(out)')], limit=1)
        partnerflows = self.env['edi.tools.edi.partnerflow'].search([('flow_id', '=', flow.id), ('partnerflow_active', '=', True)])
        creation_date_start = datetime.strftime(datetime.utcnow(), '%Y-%m-%d 00:00:00')
        for partnerflow in partnerflows:
            import pdb; pdb.set_trace()

            document_flow = self.env['edi.tools.edi.flow'].search([('model', '=', 'account.invoice'), ('name', '=', 'INVOIC D96A(out)')], limit=1)
            documents = self.env['edi.tools.edi.document.outgoing'].search([
                ('partner_id', '=', partnerflow.partnerflow_id.id),
                ('flow_id', '=', document_flow.id),
                ('create_date', '>=', creation_date_start)
            ])
            if len(documents) == 0:
                next
            content = documents.edi_export_edi_invoic_overview()
            document_name = "%s-%s" % (partnerflow.partnerflow_id.name, datetime.strftime(datetime.utcnow(), DEFAULT_SERVER_DATE_FORMAT))
            self.env['edi.tools.edi.document.outgoing'].create_from_content(document_name, content, partnerflow.partnerflow_id.id, 'edi.tools.edi.document.outgoing', 'send_edi_export_edi_invoic_overview', type='STRING')
