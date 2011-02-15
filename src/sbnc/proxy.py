from sbnc import irc, timer, event
from sbnc.event import Event

class Proxy():
    def __init__(self):
        self.irc_factory = irc.ConnectionFactory(irc.IRCConnection)

        self.client_factory = irc.ConnectionFactory(irc.ClientConnection)
        self.client_factory.new_connection_event.add_handler(self._new_client_handler)

        self.users = {}

        self.users['shroud'] = ProxyUser(self, 'shroud')
        self.users['shroud'].password = 'keks'

        #self.users['thommey'] = ProxyUser(self, 'thommey')
        #self.users['thommey'].password = 'keks'

    def _new_client_handler(self, evt, factory, clientobj):
        clientobj.authentication_event.add_handler(self._client_authentication_handler, Event.LOW_PRIORITY)
        clientobj.registration_event.add_handler(self._client_registration_handler, Event.LOW_PRIORITY)

        clientobj.authentication_service = self
            
    def _client_authentication_handler(self, evt, clientobj, username, password):
        if not username in self.users:
            return None
        
        userobj = self.users[clientobj.me.user]
        
        if userobj.password != password:
            return None
        
        clientobj.owner = userobj
        evt.stop_handlers()

    def _client_registration_handler(self, event, clientobj):
        clientobj.owner._client_registration_handler(event, clientobj)  

class ProxyUser(object):
    def __init__(self, proxy, name):
        self.proxy = proxy
        self.name = name
        self.password = None
        
        self.irc_connection = None
        self.client_connections = []
        
        self.reconnect_to_irc()

    def reconnect_to_irc(self):
        if self.irc_connection != None:
            self.irc_connection.close('Reconnecting.')

        self.irc_connection = self.proxy.irc_factory.create(address=('irc.quakenet.org', 6667))
        self.irc_connection.reg_nickname = self.name
        self.irc_connection.reg_username = 'sbncng'
        self.irc_connection.reg_realname = 'sbncng client'
        
        self.irc_connection.command_received_event.add_handler(self._irc_command_handler)
        self.irc_connection.connection_closed_event.add_handler(self._irc_closed_handler)
        
        self.irc_connection.start()

    def _irc_closed_handler(self, evt, ircobj):
        for clientobj in self.client_connections:
            for channel in clientobj.channels:
                clientobj.send_message('KICK', channel, clientobj.me.nick,
                                       'You were disconnected from the IRC server.',
                                       prefix=clientobj.server)

            clientobj.channels = []
        
        self.reconnect_to_irc()

    def _client_closed_handler(self, evt, clientobj):
        self.client_connections.remove(clientobj)

    def _client_registration_handler(self, evt, clientobj):
        clientobj.connection_closed_event.add_handler(self._client_closed_handler)
        self.client_connections.append(clientobj)

        if self.irc_connection.registered and clientobj.me.nick != self.irc_connection.me.nick:
            clientobj.send_message('NICK', self.irc_connection.me.nick, prefix=clientobj.me)
            clientobj.me.nick = self.irc_connection.me.nick

            self.irc_connection.send_message('NICK', clientobj.me.nick)

        timer.Timer.create(0, self._client_post_registration_timer, clientobj)

        if self.irc_connection != None:
            clientobj.motd = self.irc_connection.motd
            clientobj.isupport = self.irc_connection.isupport
            clientobj.channels = self.irc_connection.channels
            clientobj.nicks = self.irc_connection.nicks

        clientobj.command_received_event.add_handler(self._client_command_handler)
        clientobj.command_events['TESTDISCONNECT'].add_handler(self._client_testdisconnect_handler)

    def _client_post_registration_timer(self, clientobj):
        for channel in self.irc_connection.channels:
            clientobj.send_message('JOIN', channel, prefix=self.irc_connection.me)
            clientobj.process_line('TOPIC %s' % (channel))
            clientobj.process_line('NAMES %s' % (channel))

    def _client_command_handler(self, evt, clientobj, command, prefix, params):
        command = command.upper();

        if command in ['PASS', 'USER', 'QUIT']:
            return

        if self.irc_connection == None or (not self.irc_connection.registered and command != 'NICK'):
            return

        self.irc_connection.send_message(command, prefix=prefix, *params)
        evt.stop_handlers(event.Event.BUILTIN_PRIORITY)

    def _client_testdisconnect_handler(self, evt, clientobj, prefix, params):
        self.irc_connection.close('Fail.')
        self.irc_connection = None

    def _irc_command_handler(self, evt, ircobj, command, prefix, params):
        if not ircobj.registered:
            return
        
        command = command.upper();

        if command in ['ERROR']:
            return
    
        for clientobj in self.client_connections:
            if not clientobj.registered:
                continue
            
            if prefix == ircobj.server:
                mapped_prefix = clientobj.server
            else:
                mapped_prefix = prefix

            clientobj.send_message(command, prefix=mapped_prefix, *params)

    # TODO: irc_registration event, needs to force-change client's nick if different
    # from the irc connection