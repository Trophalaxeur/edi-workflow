{
    'name': 'edi_routes_stock_eazystock',
    'summary': 'Send stock_moves to Eazystock in CSV format using the EDI framework',
    'version': '0.7',
    'category': 'EDI Tools',
    'description': "Eazystock Transactional Data EDI integration",
    'author': 'Dimitri Verhelst Consulting OU',
    'website': 'http://www.divecon.eu/',
    'sequence': 9,
    'depends': [
        'edi_tools',
        'edi_stock_enable',
        'stock',
    ],
    'data': [
        'data/config.xml',
    ],
    'demo': [
    ],
    'test': [
    ],
    'css': [
    ],
    'images': [
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
