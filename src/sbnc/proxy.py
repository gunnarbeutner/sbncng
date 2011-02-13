from sbnc import irc, timer, event

class Proxy():
    def __init__(self):
        self.irc_factory = irc.ConnectionFactory(irc.ClientConnection)

        self.client_factory = irc.ConnectionFactory(irc.ServerConnection)
        self.client_factory.new_connection_event.add_handler(self._new_client_handler)
        self.authentication_service = ProxyAuthenticationService(self)

        self.users = {}

        self.users['shroud'] = ProxyUser(self, 'shroud')
        self.users['shroud'].password = 'keks'

    def _new_client_handler(self, event, factory, clientobj):
        clientobj.registration_event.add_handler(self._client_registration_handler)
        
        clientobj.authentication_services.append(self.authentication_service)
            
    def _client_registration_handler(self, event, clientobj):
        clientobj.owner._client_registration_handler(event, clientobj)

class ProxyAuthenticationService(irc.IAuthenticationService):
    def __init__(self, proxy):
        self.proxy = proxy
    
    def authenticate(self, username, password):
        if not username in self.proxy.users:
            return None
        
        userobj = self.proxy.users[username]
        
        if userobj.password != password:
            return None
        
        return userobj

class ProxyUser(object):
    def __init__(self, proxy, name):
        self.proxy = proxy
        self.name = name
        self.password = None
        
        self.irc_connection = self.proxy.irc_factory.create(address=('irc.quakenet.org', 6667))
        self.irc_connection.reg_nickname = 'sbncng'
        self.irc_connection.reg_username = 'sbncng'
        self.irc_connection.reg_realname = 'sbncng client'
        
        self.irc_connection.command_received_event.add_handler(self._irc_command_handler)
        
        self.irc_connection.start()
        
        self.client_connections = []

    def _client_closed_handler(self, evt, clientobj):
        self.client_connections.remove(clientobj)

    def _client_registration_handler(self, event, clientobj):
        clientobj.connection_closed_event.add_handler(self._client_closed_handler)
        self.client_connections.append(clientobj)

        if clientobj.me.nick != self.irc_connection.me.nick:
            clientobj.send_message('NICK', self.irc_connection.me.nick, prefix=clientobj.me)
            clientobj.me.nick = self.irc_connection.me.nick

            self.irc_connection.send_message('NICK', clientobj.me.nick)

        timer.Timer.create(0, self._client_post_registration_timer, clientobj)

        if self.irc_connection != None:
            clientobj.motd = self.irc_connection.motd
            clientobj.isupport = self.irc_connection.isupport

        clientobj.command_received_event.add_handler(self._client_command_handler)

    def _client_post_registration_timer(self, clientobj):
        for channel in self.irc_connection.channels:
            clientobj.send_message('JOIN', channel, prefix=self.irc_connection.me)
            clientobj.process_line('TOPIC %s' % (channel))
            clientobj.process_line('NAMES %s' % (channel))

    def _client_command_handler(self, evt, clientobj, command, prefix, params):
        if not command in ['PASS', 'USER', 'QUIT']:
            self.irc_connection.send_message(command, prefix=prefix, *params)
            evt.stop_handlers(event.Event.LOW_PRIORITY)

    def _irc_command_handler(self, evt, ircobj, command, prefix, params):
        if not ircobj.registered:
            return
        
        chans = prefix.channels
        
        print list(chans)
        
        for clientobj in self.client_connections:
            if not clientobj.registered:
                continue
            
            if prefix == ircobj.server:
                mapped_prefix = clientobj.server
            else:
                mapped_prefix = prefix

            clientobj.send_message(command, prefix=mapped_prefix, *params)
