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
from sbnc import irc
from sbnc.event import Event
from sbnc.plugin import Service, ServiceRegistry
from sbnc.irc import IRCConnection, ClientConnection, ConnectionFactory
from sbnc.timer import Timer

class Proxy(Service):
    package = 'info.shroudbnc.services.proxy'
    
    version = 'wip-1'
    
    def __init__(self):
        self.irc_factory = ConnectionFactory(IRCConnection)

        self.client_factory = ConnectionFactory(irc.ClientConnection)
    
    def start(self, config_root_node):
        self._config_root = config_root_node
        self._config = self.get_plugin_config(Proxy)
        
        ClientConnection.authentication_event.add_listener(self._client_authentication_handler,
                                                           Event.Handler,
                                                           ConnectionFactory.match_factory(self.client_factory))

        ClientConnection.registration_event.add_listener(ProxyUser._client_registration_handler,
                                                  Event.PreObserver,
                                                  ConnectionFactory.match_factory(self.client_factory))
        ClientConnection.registration_event.add_listener(ProxyUser._client_post_registration_handler,
                                                  Event.PostObserver,
                                                  ConnectionFactory.match_factory(self.client_factory))

        ClientConnection.command_received_event.add_listener(ProxyUser._client_command_handler,
                                                             Event.Handler,
                                                             ConnectionFactory.match_factory(self.client_factory),
                                                             last=True)

        ClientConnection.connection_closed_event.add_listener(ProxyUser._client_closed_handler,
                                                              Event.PostObserver,
                                                              ConnectionFactory.match_factory(self.client_factory))

        IRCConnection.command_received_event.add_listener(ProxyUser._irc_command_handler,
                                                          Event.Handler,
                                                          ConnectionFactory.match_factory(self.irc_factory),
                                                          last=True)
        IRCConnection.connection_closed_event.add_listener(ProxyUser._irc_closed_handler,
                                                           Event.PreObserver,
                                                           ConnectionFactory.match_factory(self.irc_factory))
        IRCConnection.registration_event.add_listener(ProxyUser._irc_registration_handler,
                                                            Event.PreObserver,
                                                            ConnectionFactory.match_factory(self.irc_factory))
        
        self.users = {}
        
        for user_config in self._config['users']:
            self.users[user_config.name] = ProxyUser(self, user_config)
        
        self._last_reconnect = None
        Timer(10, self._reconnect_timer).start()
        
        # high-level helper events, to make things easier for plugins
        self.new_client_event = Event()
        
        self.client_registration_event = Event()
        self.client_registration_event.bind(irc.ClientConnection.registration_event,
                                            filter=ConnectionFactory.match_factory(self.client_factory))

        self.irc_registration_event = Event()
        self.irc_registration_event.bind(IRCConnection.registration_event,
                                         filter=ConnectionFactory.match_factory(self.irc_factory))

        self.client_command_received_event = Event()
        self.client_command_received_event.bind(irc.ClientConnection.command_received_event,
                                            filter=ConnectionFactory.match_factory(self.client_factory))

        self.irc_command_received_event = Event()
        self.irc_command_received_event.bind(IRCConnection.command_received_event,
                                         filter=ConnectionFactory.match_factory(self.irc_factory))

        self.client_connection_closed_event = Event()
        self.client_connection_closed_event.bind(ClientConnection.connection_closed_event,
                                         filter=ConnectionFactory.match_factory(self.irc_factory))

        self.irc_connection_closed_event = Event()
        self.irc_connection_closed_event.bind(IRCConnection.connection_closed_event,
                                         filter=ConnectionFactory.match_factory(self.irc_factory))

    def _client_authentication_handler(self, evt, clientobj, username, password):
        if not username in self.users:
            return Event.Continue
        
        userobj = self.users[clientobj.me.user]
        
        if not userobj.check_password(password):
            return Event.Continue
        
        clientobj.owner = userobj

        return Event.Handled

    def create_user(self, name):
        if name in self.users:
            raise ValueError('User already exists.')
        
        user_config = self._config['users'][name]
        user = ProxyUser(self, user_config)
        self.users[name] = user
        
        # TODO: event
        
        return user

    def remove_user(self, name):
        # TODO: event

        del self.users[name]
        del self.config['users'][name]
        
    def _reconnect_timer(self):
        if self._last_reconnect != None and \
                self._last_reconnect > time() - 60:
            return True
        
        for userobj in self.users.values():
            if userobj.irc_connection != None or (userobj.last_reconnect != None and \
                    userobj.last_reconnect > time() - 120):
                continue

            self._last_reconnect = time()
            userobj.reconnect_to_irc()
            
            break
        
        return True
    
    def get_plugin_config(self, plugin_cls):
        return self._config_root[plugin_cls.package]

class ProxyUser(object):
    def __init__(self, proxy, user_config):
        self.proxy = proxy
        self.name = user_config.name
        
        self._config_root = user_config
        self._config = self.get_plugin_config(Proxy)
        
        self.irc_connection = None
        self.client_connections = []
        
    def get_plugin_config(self, plugin_cls):
        return self._config_root[plugin_cls.package]

    def reconnect_to_irc(self):
        if self.irc_connection != None:
            self.irc_connection.close('Reconnecting.')

        server_address = self._config.get('server_address', None)

        if server_address == None:
            # TODO: trigger event, so scripts know we won't reconnect
            return

        self.irc_connection = self.proxy.irc_factory.create(address=tuple(server_address))
        self.irc_connection.owner = self
        self.irc_connection.reg_nickname = self._config.get('nick', self.name)
        self.irc_connection.reg_username = self._config.get('username', self.name)
        self.irc_connection.reg_realname = self._config.get('realname', 'sbncng User')
        
        self.irc_connection.start()
        
        self.last_reconnect = time()

    @staticmethod
    def _irc_closed_handler(evt, ircobj):
        self = ircobj.owner

        for clientobj in self.client_connections:
            for channel in clientobj.channels:
                clientobj.send_message('KICK', channel, clientobj.me.nick,
                                       'You were disconnected from the IRC server.',
                                       prefix=clientobj.server)

            clientobj.channels = []
            
        self.irc_connection = None
        
    @staticmethod
    def _client_closed_handler(evt, clientobj):
        self = clientobj.owner
        
        if self == None:
            return
        
        self.client_connections.remove(clientobj)
        
    @staticmethod
    def _client_registration_handler(evt, clientobj):
        self = clientobj.owner
        
        self.client_connections.append(clientobj)

        if self.irc_connection != None and self.irc_connection.registered and \
                clientobj.me.nick != self.irc_connection.me.nick:
            clientobj.send_message('NICK', self.irc_connection.me.nick, prefix=clientobj.me)
            clientobj.me.nick = self.irc_connection.me.nick

            self.irc_connection.send_message('NICK', clientobj.me.nick)

        if self.irc_connection != None:
            clientobj.motd = self.irc_connection.motd
            clientobj.isupport = self.irc_connection.isupport
            clientobj.channels = self.irc_connection.channels
            clientobj.nicks = self.irc_connection.nicks

    @staticmethod
    def _client_post_registration_handler(evt, clientobj):
        self = clientobj.owner
        
        if self.irc_connection == None:
            return
        
        if self.irc_connection.away:
            clientobj.send_message('306', 'You have been marked as being away')
        
        for channel in self.irc_connection.channels:
            clientobj.send_message('JOIN', channel, prefix=self.irc_connection.me)
            clientobj.process_line('TOPIC %s' % (channel))
            clientobj.process_line('NAMES %s' % (channel))
            
    @staticmethod
    def _irc_registration_handler(evt, ircobj):
        self = ircobj.owner

        for clientobj in self.client_connections:
            if clientobj.me.nick != ircobj.me.nick:
                clientobj.send_message('NICK', self.irc_connection.me.nick, prefix=clientobj.me)
                clientobj.me.nick = self.irc_connection.me.nick

    @staticmethod
    def _client_command_handler(evt, clientobj, command, nickobj, params):
        self = clientobj.owner
        
        if self == None or not clientobj.registered:
            return Event.Continue
        
        command = command.upper();

        if command in ['PASS', 'USER', 'QUIT'] or evt.handled:
            return Event.Continue

        if self.irc_connection == None or (not self.irc_connection.registered and command != 'NICK'):
            return Event.Continue

        self.irc_connection.send_message(command, prefix=nickobj, *params)
        
        return Event.Handled

    @staticmethod
    def _irc_command_handler(evt, ircobj, command, nickobj, params):
        self = ircobj.owner
        
        if not ircobj.registered:
            return Event.Continue
        
        command = command.upper();

        if command in ['ERROR']:
            return Event.Continue
    
        for clientobj in self.client_connections:
            if not clientobj.registered:
                continue
            
            if nickobj == ircobj.server:
                mapped_prefix = clientobj.server
            else:
                mapped_prefix = nickobj

            clientobj.send_message(command, prefix=mapped_prefix, *params)

        return Event.Handled

    def check_password(self, password):
        return password != None and self._config.get('password', None) == password

    def _get_last_reconnect(self):
        return self._config.get('last_reconnect', None)
    
    def _set_last_reconnect(self, value):
        self._config.set('last_reconnect', value)

    last_reconnect = property(_get_last_reconnect, _set_last_reconnect)
    
    def _get_password(self):
        return self._config.get('password', None)
    
    def _set_password(self, value):
        self._config.set('password', value)

    password = property(_get_password, _set_password)

    def _get_admin(self):
        return self._config.get('admin', None)
    
    def _set_admin(self, value):
        self._config.set('admin', value)

    admin = property(_get_admin, _set_admin)

ServiceRegistry.register(Proxy)