from odoo import fields, models, api

class edi_tools_config_settings(models.TransientModel):
    _inherit = 'res.config.settings'

    edi_root_directory = fields.Char(size=256,string= 'Edi Root Directory')

    @api.model
    def get_values(self):
        res = super(edi_tools_config_settings, self).get_values()
        ICPSudo = self.env['ir.config_parameter'].sudo()
        res.update(
            edi_root_directory = ICPSudo.get_param('edi.edi_root_directory', default='/EDI')
        )
        return res

    @api.multi
    def set_values(self):
        super(edi_tools_config_settings, self).set_values()
        ICPSudo = self.env['ir.config_parameter'].sudo()
        ICPSudo.set_param("edi.edi_root_directory", self.edi_root_directory)