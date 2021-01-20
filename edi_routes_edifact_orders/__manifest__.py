{
    'name': 'EDI Edifact Orders',
    'summary': 'EDI edifact Orders route import a sale order.',
    'version': '13.0.1',
    'category': 'EDI Tools',
    'author': 'Florian Lefevre / Clubit BVBA',
    'depends': [
        'edi_tools',
        'sale',
        'point_of_sale', # Used to link partner with barcode
        # 'edi_sale_enable',
        'edi_edifact_parser',
    ],
    'data': [
        'data/config.xml',
    ],
    'installable': True,
    'auto_install': False,
}
