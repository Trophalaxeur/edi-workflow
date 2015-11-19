# -*- coding: utf-8 -*-
#    Author: Dimitri Verhelst
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

{'name': 'EDI for EDI',
 'summary': 'Enable sending EDI for EDI objects',
 'version': '0.1',
 'description': """
EDI message based on other EDI messages
=======================================

This module allows you to select EDI outgoing documents in order to create an overview of what has been sent.
This is where things go meta.
 """,
 'author': "Clubit BVBA",
 'category': 'Sales',
 'license': 'AGPL-3',
 'images': [],
 'depends': ['edi_tools'],
 'data': [
     'wizards/edi.xml',
 ],
 'auto_install': False,
 'installable': True,
 }
