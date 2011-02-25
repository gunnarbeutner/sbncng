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
from sbnc.event import Event

proxy_svc = ServiceRegistry.get(Proxy.package)

class AwayCommandPlugin(Plugin):
    """Provides the 'away' setting and related functionality."""
    
    package = 'info.shroudbnc.plugins.awaycmd'
    name = 'awaycmd'
    description = __doc__

    def __init__(self):
        proxy_svc.client_registration_event.add_listener(self._client_registration_handler,
                                                         Event.PostObserver)
        # TODO: implement proxy_svc.client_connection_closed_event
        # TODO: implement setting

    def _client_registration_handler(self, evt, clientobj):
        clientobj.connection_closed_event.add_listener(self._client_closed_handler, Event.PostObserver)
        
        if clientobj.owner.irc_connection == None or not clientobj.owner.irc_connection.registered:
            return

        clientobj.owner.irc_connection.send_message('AWAY')
        
    def _client_closed_handler(self, evt, clientobj):
        if clientobj.owner.irc_connection == None or not clientobj.owner.irc_connection.registered:
            return

        if 'away' not in clientobj.owner.config or clientobj.owner.config['away'] == '':
            return
        
        message = clientobj.owner.config['away']
    
        if len(clientobj.owner.client_connections) == 0 or \
                clientobj.owner.client_connections == [clientobj]:
            clientobj.owner.irc_connection.send_message('AWAY', message)

ServiceRegistry.register(AwayCommandPlugin)