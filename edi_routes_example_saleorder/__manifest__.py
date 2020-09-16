{
    'name': 'edi_routes_example_saleorder',
    'summary': 'EDI example route that shows you how to export and import a sale order.',
    'version': '13.0.1',
    'category': 'EDI Tools',
    'author': 'Florian Lefevre / Clubit BVBA',
    'depends': [
        'edi_tools',
        'sale',
        'edi_sale_enable',
    ],
    'data': [
        'data/config.xml',
    ],
    'installable': True,
    'auto_install': False,
}
