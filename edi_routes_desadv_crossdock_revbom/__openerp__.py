{
    'name': 'edi_routes_desadv_crossdock_revbom',
    'summary': 'Edifact DESADV (tailored for crossdocking with reverse BOM) communication using the EDI framework',
    'version': '1.0',
    'category': 'EDI Tools',
    'author': 'Clubit BVBA',
    'website': 'http://www.clubit.be',
    'depends': [
        'edi_routes_desadv_crossdock',
        'edi_routes_desadv',
        'stock_packaging_weight',
    ],
    'data': [
    ],
    'installable': True,
    'auto_install': False,
}
