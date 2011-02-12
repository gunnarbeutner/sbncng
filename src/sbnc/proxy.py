from sbnc import irc, timer, event

class Proxy(object):
    def __init__(self):
        self.irc_factory = irc.ConnectionFactory(irc.ClientConnection)
        self.client_factory = irc.ConnectionFactory(irc.ServerConnection)

        self.client_factory.new_connection_event.add_handler(self.new_client_handler)
        
        self.irc_connection = self.irc_factory.create(addr=('irc.quakenet.org', 6667))
        self.irc_connection.reg_nickname = 'sbncng'
        self.irc_connection.reg_username = 'sbncng'
        self.irc_connection.reg_realname = 'sbncng client'
        
        self.irc_connection.command_received_event.add_handler(self.irc_command_handler)
        
        self.irc_connection.start()
        
        self.client_connections = []
        
    def new_client_handler(self, event, factory, clientobj):
        self.client_connections.append(clientobj)
        
        clientobj.registration_event.add_handler(self.client_registration_handler)
        clientobj.connection_closed_event.add_handler(self.client_closed_handler)
            
    def client_closed_handler(self, evt, clientobj):
        self.client_connections.remove(clientobj)
    
    def client_registration_handler(self, event, clientobj):
        timer.Timer.create(0, self.client_post_registration_timer, clientobj)

        if self.irc_connection != None:
            clientobj.motd = self.irc_connection.motd
            clientobj.isupport = self.irc_connection.isupport

        clientobj.command_received_event.add_handler(self.client_command_handler)
            
    def client_post_registration_timer(self, clientobj):
        if clientobj.hostmask.nick != self.irc_connection.hostmask.nick:
            clientobj.send_message('NICK', self.irc_connection.hostmask.nick, prefix=clientobj.hostmask)
            clientobj.hostmask.nick = self.irc_connection.hostmask.nick

            self.irc_connection.send_message('NICK', clientobj.hostmask.nick)
        
        for channel in self.irc_connection.channels:
            clientobj.send_message('JOIN', channel, prefix=self.irc_connection.hostmask)
            clientobj.process_line('TOPIC %s' % (channel))
            clientobj.process_line('NAMES %s' % (channel))
    
    def client_command_handler(self, evt, clientobj, command, prefix, params):
        if not clientobj.registered:
            return
        
        if not command in ['PASS', 'USER', 'QUIT']:
            self.irc_connection.send_message(command, prefix=prefix, *params)
            evt.stop_handlers(event.Event.LOW_PRIORITY)
        
    def irc_command_handler(self, evt, ircobj, command, prefix, params):
        if not ircobj.registered:
            return
        
        for clientobj in self.client_connections:
            clientobj.send_message(command, prefix=prefix, *params)
