from odoo import models, api
from odoo.tools.translate import _
from odoo.exceptions import ValidationError

class edi_tools_edi_wizard_ready(models.TransientModel):
    _name = 'edi.tools.edi.wizard.ready'
    _description = 'Mark EDI documents as ready'


    ''' edi.tools.edi.wizard.ready:ready()
        ------------------------------------------
        This method is used by the EDI wizard to push
        multiple documents to the workflow "ready" state.
        ------------------------------------------------- '''
    
    def ready(self):

        # Get the selected documents
        # --------------------------
        for record in self:
            ids = self.env.context.get('active_ids',[])
            if not ids:
                raise ValidationError(_("You did not provide any documents to process!"))
            # Push each document to ready
            # ---------------------------
            for document in self.env['edi.tools.edi.document.incoming'].browse(ids):
                if document.state == 'new' or document.state == 'in_error':
                    document.action_ready()
