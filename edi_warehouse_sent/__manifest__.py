{
    'name': 'edi_warehouse_sent',
    'summary': 'Flag added to relevant documents indicating that communication is sent to the warehouse partner.',
    'version': '1.0',
    'category': 'EDI Tools',
    'author': 'Clubit BVBA',
    'website': 'http://www.clubit.be',
    'depends': [
        'edi_stock_enable',
    ],
    'data': [
        'views/stock_view.xml'
    ],
    'installable': True,
    'auto_install': False,
}
