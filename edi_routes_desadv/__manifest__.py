{
    'name': 'edi_routes_desadv',
    'summary': 'Edifact DESADV communication using the EDI framework',
    'version': '13.0.1',
    'category': 'EDI Tools',
    'author': 'Florian Lefevre / Clubit BVBA',
    'depends': [
        'edi_tools',
        'edi_stock_enable',
        'stock',
        'delivery',
    ],
    'data': [
        'views/stock_view.xml',
        'wizard/delivery_out.xml',
    ],
    'installable': True,
    'auto_install': False,
}
