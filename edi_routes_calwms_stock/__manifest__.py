{
    'name': 'edi_routes_calwms_stock',
    'summary': 'Inventory route for CALWMS communication using the EDI framework',
    'version': '1.0',
    'category': 'EDI Tools',
    'author': 'Dimitri Verhelst Consulting OU',
    'website': 'http://www.clubit.be',
    'depends': [
        'edi_tools',
        'edi_stock_enable',
        'stock',
    ],
    'data': [
        'data/config.xml',
    ],
    'installable': True,
    'auto_install': False,
}
