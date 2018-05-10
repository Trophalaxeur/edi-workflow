from odoo import models, fields, api, _

class res_partner(models.Model):
    _inherit = "res.partner"
    
    targo_reference = fields.Char(size=64)
    discount_1_days = fields.Integer(string="Discount 1 days")
    discount_2_days = fields.Integer(string="Discount 2 days")
    discount_3_days = fields.Integer(string="Discount 3 days")
    discount_1_perc = fields.Float(string="Discount 1 percentage")
    discount_2_perc = fields.Float(string="Discount 2 percentage")
    discount_3_perc = fields.Float(string="Discount 3 percentage")

