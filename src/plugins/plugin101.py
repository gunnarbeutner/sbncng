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
from sbnc.proxy import Proxy
from plugins.ui import UIPlugin

proxy_svc = ServiceRegistry.get(Proxy.package)
ui_svc = ServiceRegistry.get(UIPlugin.package)

class TestPlugin(Plugin):
    """Just a test plugin."""

    package = 'info.shroudbnc.plugins.plugin101'
    name = 'Test Plugin 101'
    description = __doc__
    
    def __init__(self):
        try:
            user = proxy_svc.create_user('shroud')
            user_config_proxy = user.get_plugin_config(Proxy)
            user_config_proxy.set('password', 'keks')
            user_config_proxy.set('admin', True)
            user_config_proxy.set('away', 'moo!')
            user_config_proxy.set('server_address', ('irc.quakenet.org', 6667))
        except ValueError:
            pass
        
        ui_svc.register_command('moo', self._cmd_moo_handler, 'User', 'says moo', 'Syntax: moo')

    def _cmd_moo_handler(self, clientobj, params, notice):
        ui_svc.send_sbnc_reply(clientobj, 'Moo!', notice)

ServiceRegistry.register(TestPlugin)
