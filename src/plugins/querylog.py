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

from time import time
from datetime import datetime
from sbnc.plugin import Plugin, ServiceRegistry
from sbnc.event import Event
from sbnc.irc import match_command
from sbnc.proxy import Proxy
from plugins.ui import UIPlugin

proxy_svc = ServiceRegistry.get(Proxy.package)
ui_svc = ServiceRegistry.get(UIPlugin.package)

class QueryLogPlugin(Plugin):
    """Implements query log functionality."""
    
    package = 'info.shroudbnc.plugins.querylog'
    name = 'querylog'
    description = __doc__

    def __init__(self):
        proxy_svc.irc_command_received_event.add_listener(self._irc_privmsg_handler,
                                                          Event.PostObserver,
                                                          filter=match_command('PRIVMSG'))

        # register a client login handler so we can notify users about new messages
        proxy_svc.client_registration_event.add_listener(self._client_registration_event,
                                                         Event.PostObserver)

        # and finally some handlers for /sbnc commands
        ui_svc.register_command('read', self._cmd_read_handler, 'User', 'plays your message log',
                                'Syntax: read\nDisplays your private log.')
        ui_svc.register_command('erase', self._cmd_erase_handler, 'User', 'erases your message log',
                                'Syntax: erase\nErases your private log.')

    def _client_registration_event(self, evt, clientobj):
        querylog = self.get_querylog(clientobj.owner)
        messages = querylog.attributes
        
        if len(messages) == 0:
            return
        
        ui_svc.send_sbnc_reply(clientobj, 'You have new messages. Use \'/msg -sBNC read\' ' +
                               'to view them.', notice=False)
    
    def _irc_privmsg_handler(self, evt, ircobj, command, nickobj, params):
        if len(params) < 2:
            return
        
        if evt.handled:
            return
        
        if ircobj.owner == None or len(ircobj.owner.client_connections) > 0:
            return
        
        target = params[0]
        text = params[1]
        
        if ircobj.me.nick != target:
            return
                
        item = {
            'timestamp': time(),
            'source': str(nickobj),
            'text': text
        }

        querylog = self.get_querylog(ircobj.owner)
        querylog.append(item)
    
    def get_querylog(self, userobj):
        user_config = userobj.get_plugin_config(self.__class__)
        return user_config['querylog']
    
    def _cmd_read_handler(self, clientobj, params, notice):
        querylog = self.get_querylog(clientobj.owner)
        
        messages = querylog.attributes
        
        if len(messages) == 0:
            ui_svc.send_sbnc_reply(clientobj, 'Your personal log is empty.', notice)
            return
        
        for message_node in messages:
            message = message_node.value
            ui_svc.send_sbnc_reply(clientobj, '[%s] %s: %s' %
                                   (datetime.utcfromtimestamp(message['timestamp']),
                                   message['source'], message['text']), notice)
            
        if notice:
            erasecmd = '/sbnc erase'
        else:
            erasecmd = '/msg -sBNC erase'
            
        ui_svc.send_sbnc_reply(clientobj, 'End of LOG. Use \'%s\' to ' % (erasecmd) +
                               'remove this log.', notice)
    
    def erase_querylog(self, userobj):
        querylog = self.get_querylog(userobj)
        querylog.clear()
    
    def _cmd_erase_handler(self, clientobj, params, notice):
        querylog = self.get_querylog(clientobj.owner)
        messages = querylog.attributes
        
        if len(messages) == 0:
            ui_svc.send_sbnc_reply(clientobj, 'Your personal log is empty.', notice)
            return

        self.erase_querylog(clientobj.owner)
        
        ui_svc.send_sbnc_reply(clientobj, 'Done.', notice)
    
ServiceRegistry.register(QueryLogPlugin)
