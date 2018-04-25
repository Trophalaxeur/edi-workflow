from odoo import models, fields, api
from odoo.tools.translate import _
from odoo.exceptions import ValidationError

class edi_tools_settings_connection(models.Model):
    _name = "edi.tools.settings.connection"

    setting = fields.Many2one('edi.tools.settings', 'Settings', ondelete='cascade', required=True, select=True)
    partner = fields.Many2one('res.partner', 'Partner', ondelete='cascade', required=True, select=True)
    is_active = fields.Boolean('Active')
    name = fields.Char('Name', size=50)
    url = fields.Char('Address', size=256, required=True)
    port = fields.Integer('Port', required=True)
    user = fields.Char('User', size=50, required=True)
    password = fields.Char('Password', size=100, required=True, password=True)


class edi_tools_settings(models.Model):
    _name = "edi.tools.settings"
    _description = "Settings model for Clubit Tools"

    no_of_processes = fields.Integer('Number of processes', required=True)
    connections = fields.One2many('edi.tools.settings.connection', 'setting', 'Connections')

    @api.model
    def create(self, vals):
        if self.search([]):
            raise ValidationError(_("Only 1 settings record allowed."))
        return super(edi_tools_settings, self).create(vals)

    @api.model
    def get_settings(self):
        ids = self.search(cr, uid, [])
        if ids:
            return self.browse(cr, uid, ids[0])
        return False

    @api.model
    def get_connection(self, partner_id, name=False):
        settings = self.get_settings()
        if name:
            return next((x for x in settings.connections if x.partner.id == partner_id and x.name == name),None)
        return next((x for x in settings.connections if x.partner.id == partner_id),None)
