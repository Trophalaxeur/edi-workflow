{
    'name': 'edi_partner_sent',
    'summary': 'Flag added to relevant documents indicating that communication is sent to the external processing partner.',
    'version': '1.0',
    'category': 'EDI Tools',
    'author': 'Clubit BVBA',
    'website': 'http://www.clubit.be',
    'depends': [
        'edi_stock_enable',
        'edi_account_enable'
    ],
    'data': [
        'views/stock_view.xml',
        'views/account_view.xml'
    ],
    'installable': True,
    'auto_install': False,
}
