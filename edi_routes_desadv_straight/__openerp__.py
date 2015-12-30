{
    'name': 'edi_routes_desadv_straight',
    'summary': 'Edifact DESADV (no crossdocking) communication using the EDI framework',
    'version': '1.0',
    'category': 'EDI Tools',
    'author': 'Clubit BVBA',
    'website': 'http://www.clubit.be',
    'depends': [
        'edi_routes_desadv',
        'stock_packaging_weight',
    ],
    'data': [
        'data/config.xml',
    ],
    'installable': True,
    'auto_install': False,
}
