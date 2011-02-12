from sbnc import irc, timer, event

class Proxy(object):
    irc_factory = irc.ConnectionFactory(irc.ClientConnection)
    client_factory = irc.ConnectionFactory(irc.ServerConnection)

    def __init__(self):
        self.irc_factory = irc.ConnectionFactory(irc.ClientConnection)
        self.client_factory = irc.ConnectionFactory(irc.ServerConnection)

        self.client_factory.new_connection_event.add_handler(self.new_client_handler)
        
        self.irc_connection = Proxy.irc_factory.create(addr=('irc.quakenet.org', 6667))
        self.irc_connection.attempted_nickname = 'sbncng'
        self.irc_connection.username = 'sbncng'
        self.irc_connection.realname = 'sbncng client'
        
        self.irc_connection.command_received_event.add_handler(self.irc_command_handler)
        
        self.irc_connection.start()
        
        self.client_connections = []
        
    def new_client_handler(self, event, factory, clientobj):
        self.client_connections.append(clientobj)
        
        clientobj.registration_event.add_handler(self.client_registration_handler)
        clientobj.connection_closed_event.add_handler(self.client_closed_handler)
        
        if irc != None:
            clientobj.motd = self.irc_connection.motd
            clientobj.isupport = self.irc_connection.isupport
    
    def client_closed_handler(self, evt, clientobj):
        self.client_connections.remove(clientobj)
    
    def client_registration_handler(self, event, clientobj):
        if clientobj.nickname != self.irc_connection.nickname:
            timer.Timer.create(0, self.client_post_registration_timer, clientobj)
    
        clientobj.command_received_event.add_handler(self.client_command_handler)
            
    def client_post_registration_timer(self, clientobj):
        clientobj.send_message('NICK', self.irc_connection.nickname, prefix=clientobj.get_hostmask())
        clientobj.nickname = self.irc_connection.nickname
    
    def client_command_handler(self, evt, clientobj, command, prefix, params):
        if not clientobj.registered:
            return
        
        if command != 'QUIT':
            self.irc_connection.send_message(command, prefix=prefix, *params)
        
        evt.stop_handlers(event.Event.LOW_PRIORITY)
        
    def irc_command_handler(self, evt, ircobj, command, prefix, params):
        if not ircobj.registered:
            return
        
        for clientobj in self.client_connections:
            clientobj.send_message(command, prefix=prefix, *params)
