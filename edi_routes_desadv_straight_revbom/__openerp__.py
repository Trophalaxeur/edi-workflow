{
    'name': 'edi_routes_desadv_straight_revbom',
    'summary': 'Edifact DESADV (no crossdocking) communication using the EDI framework, Reverse BOM',
    'version': '1.0',
    'category': 'EDI Tools',
    'author': 'Clubit BVBA',
    'website': 'http://www.clubit.be',
    'depends': [
        'edi_routes_desadv',
        'edi_routes_desadv_straight',
        'stock_packaging_weight',
    ],
    'data': [
    ],
    'installable': True,
    'auto_install': False,
}
