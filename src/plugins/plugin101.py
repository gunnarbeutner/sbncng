# sbncng - an object-oriented framework for IRC
# Copyright (C) 2011 Gunnar Beutner
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA  02111-1307, USA.

from sbnc.plugin import Plugin, ServiceRegistry

class TestPlugin(Plugin):
    name = 'Test Plugin 101'
    description = 'Just a test plugin.'

    def __init__(self):
        sr = ServiceRegistry.get_instance()
        proxy = sr.get('info.shroudbnc.services.proxy')
        
        user = proxy.create_user('shroud')
        user.config['password'] = 'keks'

sr = ServiceRegistry.get_instance()        
sr.register('info.shroudbnc.plugins.plugin101', TestPlugin())
