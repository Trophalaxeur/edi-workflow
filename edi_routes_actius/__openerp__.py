{
    'name': 'edi_routes_actius',
    'summary': 'Send deliveries to ACTIUS using the EDI framework',
    'version': '1.0',
    'category': 'EDI Tools',
    'author': 'Clubit BVBA',
    'website': 'http://www.clubit.be',
    'depends': [
        'edi_tools',
        'stock_bom_pickpack',
        'edi_stock_enable',
        'stock',
        'sale_stock_incoterm_chainer',
        'product_customerinfo',
        'delivery_instructions',
        'edi_routes_invoice_expertm',
        ],
    'data': [
        'data/config.xml',
        'views/stock_view.xml',
    ],
    'installable': True,
    'auto_install': False,
}
