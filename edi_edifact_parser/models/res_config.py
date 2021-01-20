from odoo import fields, models, api

class EdiEdifactParserResConfig(models.TransientModel):
    _inherit = 'res.config.settings'

    bots_config_dir = fields.Char(size=256,string= 'Bots Config Directory')

    @api.model
    def get_values(self):
        res = super(EdiEdifactParserResConfig, self).get_values()
        ICPSudo = self.env['ir.config_parameter'].sudo()
        res.update(
            bots_config_dir = ICPSudo.get_param('edi.bots_config_dir', default='config')
        )
        return res

    
    def set_values(self):
        super(EdiEdifactParserResConfig, self).set_values()
        ICPSudo = self.env['ir.config_parameter'].sudo()
        ICPSudo.set_param("edi.bots_config_dir", self.bots_config_dir)