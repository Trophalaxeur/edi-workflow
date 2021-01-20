# -*- coding: utf-8 -*-
##############################################################################
#
#   Florian Lefevre consulting
#   Based on :
#    Trey, Kilobytes de Soluciones
#   works
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
#
##############################################################################
{
    'name': 'EDI Edifact Parser',
    'summary': 'EDIFACT base',
    'author': 'Florian Lefevre Consulting',
    'category': 'EDI Tools',
    'version': '13.0.1',
    'depends': [
        'base',
        'edi_tools',
    ],
    'data': [
        'views/res_config.xml',
    ],
    # 'external_dependencies': {
    #     'python': [
    #         'bots',
    #     ],
    # },
    'installable': True,
}
