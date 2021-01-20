{
    'name': 'EDI Edifact Orders',
    'summary': 'EDI edifact Orders route import a sale order.',
    'version': '13.0.1',
    'category': 'EDI Tools',
    'author': 'Florian Lefevre / Clubit BVBA',
    'depends': [
        'sale',
        'point_of_sale', # Used to link partner with barcode
        'edi_tools',
        'edi_edifact_parser',
        # 'edi_sale_enable',
    ],
    'data': [
        'data/config.xml',
    ],
    'installable': True,
    'auto_install': False,
}
