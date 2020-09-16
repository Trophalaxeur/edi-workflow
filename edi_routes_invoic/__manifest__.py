{
    'name': 'edi_routes_invoic',
    'summary': 'Edifact INVOIC communication using the EDI framework',
    'version': '13.0.1',
    'category': 'EDI Tools',
    'author': 'Florian Lefevre / Clubit BVBA',
    'depends': [
        'edi_tools',
        'edi_account_enable',
        'edi_routes_desadv',
        'account',
    ],
    'data': [
        'data/config.xml',
    ],
    'installable': True,
    'auto_install': False,
}
