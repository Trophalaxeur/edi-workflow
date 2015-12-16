{
    'name': 'edi_routes_vrd',
    'summary': 'Send deliveries to VRD using the EDI framework',
    'version': '1.0',
    'category': 'EDI Tools',
    'author': 'Clubit BVBA',
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
