{
    'name': 'edi_routes_invoic_revbom',
    'summary': 'Edifact INVOIC communication using the EDI framework using Reverse BOM',
    'version': '1.0',
    'category': 'EDI Tools',
    'author': 'Clubit BVBA',
    'website': 'http://www.clubit.be',
    'depends': [
        'edi_tools',
        'edi_routes_invoic',
        'edi_account_enable',
        'edi_routes_desadv',
        'account',
    ],
    'data': [
    ],
    'installable': True,
    'auto_install': False,
}
