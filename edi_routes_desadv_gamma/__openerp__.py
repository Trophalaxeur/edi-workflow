{
    'name': 'edi_routes_desadv_gamma',
    'summary': 'Edifact DESADV for Intergamma BV communication using the EDI framework',
    'version': '1.0',
    'category': 'EDI Tools',
    'author': 'Clubit BVBA',
    'website': 'http://www.clubit.be',
    'depends': [
        'edi_routes_desadv',
        'stock_packaging_weight',
        'sale_order_bomify'
    ],
    'data': [
        'data/config.xml',
    ],
    'installable': True,
    'auto_install': False,
}
