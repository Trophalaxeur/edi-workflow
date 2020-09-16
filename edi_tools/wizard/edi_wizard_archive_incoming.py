from odoo import models, api
from odoo.exceptions import ValidationError
from odoo.tools.translate import _

class edi_tools_edi_wizard_archive_incoming(models.TransientModel):
    _name = 'edi.tools.edi.wizard.archive.incoming'
    _description = 'Archive EDI Documents'

    ''' edi.tools.edi.wizard.archive.incoming:archive()
        --------------------------------------------------
        This method is used by the EDI wizard to push
        multiple documents to the workflow "archived" state.
        ---------------------------------------------------- '''
    @api.multi
    def archive(self):
        # Get the selected documents
        # --------------------------
        for record in self:
            ids = self.env.context.get('active_ids',[])
            if not ids:
                raise ValidationError(_("You did not provide any documents to archive!"))
            # Push each document to archived
            # ------------------------------
            for document in self.env['edi.tools.edi.document.incoming'].browse(ids):
                if document.state in ['new','ready','processed','in_error']:
                    document.action_archive()
            return {'type': 'ir.actions.act_window_close'}

