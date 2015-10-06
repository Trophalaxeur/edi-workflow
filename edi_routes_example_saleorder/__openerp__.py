{
    'name': 'edi_routes_example_saleorder',
    'summary': 'EDI example route that shows you how to export and import a sale order.',
    'version': '1.0',
    'category': 'EDI Tools',
    'author': 'Clubit BVBA',
    'website': 'http://www.clubit.be',
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
