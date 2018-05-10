{
    'name': 'edi_routes_invoice_targo',
    'summary': 'Send Invoices to TARGO in CSV format using the EDI framework',
    'version': '11.1',
    'category': 'EDI Tools',
    'author': 'Dimitri Verhelst Consulting OU',
    'website': 'http://www.clubit.be',
    'depends': [
        'edi_tools',
        'edi_account_enable',
        'account',
    ],
    'data': [
        'data/config.xml',
    ],
    'installable': True,
    'auto_install': False,
}
