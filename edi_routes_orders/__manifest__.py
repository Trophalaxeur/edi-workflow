# -*- coding: utf-8 -*-
#    Author: Florian Lefevre
#    Original Author: Jan Vereecken
#    Source: http://www.clubit.be
#    Copyright 2015 Clubit BVBA
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.

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
    'version': '13.0.1',
    'category': 'EDI Tools',
    'author': "Florian Lefevre / Clubit BVBA",
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
