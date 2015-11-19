{
    'name': 'edi_routes_edi_invoic_overview',
    'summary': 'EDI Invoic Overview HTML mail',
    'description': """
EDI Invoic Overview in HTML for Mailing
=======================================

This module allows you to select INVOIC D96A(out) outgoing documents in order to create an overview of what has been sent.
    """,
    'version': '1.0',
    'category': 'EDI Tools',
    'author': 'Clubit BVBA',
    'website': 'http://www.clubit.be',
    'depends': [
        'edi_routes_invoic',
        'edi_edi_enable',
        'edi_tools',
    ],
    'data': [
        'data/config.xml',
    ],
    'installable': True,
    'auto_install': False,
}
