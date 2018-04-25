{
    'name': 'edi_customer_sent',
    'summary': 'Flag added to relevant documents indicating that communication is sent to the customer.',
    'version': '1.0',
    'category': 'EDI Tools',
    'author': 'Clubit BVBA',
    'website': 'http://www.clubit.be',
    'depends': [
        #'edi_routes_desadv_crossdock',
        #'edi_routes_invoic',
        'stock'
    ],
    'data': [
        'views/account_view.xml',
        'views/stock_view.xml',
    ],
    'installable': True,
    'auto_install': False,
}
