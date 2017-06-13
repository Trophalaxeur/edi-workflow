{
    'name': 'edi_routes_essers_bom',
    'summary': 'Send manufacturing orders to Essers using the EDI framework',
    'version': '1.0',
    'category': 'EDI Tools',
    'author': 'Clubit BVBA',
    'website': 'http://www.clubit.be',
    'depends': [
        'edi_tools',
        'edi_mrp_enable',
        'mrp',
        'sale_stock_reference_chainer',
        'sale_stock_incoterm_chainer',
        'product_customerinfo',
        'delivery_instructions',
        'edi_routes_invoice_expertm',
        ],
    'data': [
        'data/config.xml',
        'views/mrp_view.xml',
    ],
    'installable': True,
    'auto_install': False,
}
