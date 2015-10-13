{
    'name': 'edi_routes_orders',
    'summary': 'Edifact ORDERS communication using the EDI framework',
    'description' : """
Edifact ORDERS communication using the EDI framework
====================================================

This module implements routes for the following implementations.

    * ORDERS 93A
    * ORDERS 96A

The input format is not the original EDIFACT format, but rather the translation of this format. The original format is processed by bots (http://bots.sourceforge.net).
    """,
    'version': '1.0',
    'category': 'EDI Tools',
    'author': 'Clubit BVBA',
    'website': 'http://www.clubit.be',
    'depends': [
        'edi_tools',
        'sale',
    ],
    'data': [
        'data/config.xml',
    ],
    'installable': True,
    'auto_install': False,
}
