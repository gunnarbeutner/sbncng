import string
from collections import defaultdict
import gevent
from gevent import socket, dns
from sbnc import utils
from sbnc.event import Event

class RegistrationTimeoutError(Exception):
    pass

class BaseIRCConnection(object):    
    socket = None
    socket_addr = None
    
    registered = False
    attempted_nickname = None
    nickname = None
    username = None
    password = None
    hostname = None
    realname = None
        
    _registration_timeout = None

    def __init__(self, **kwargs):
        """Named parameters can either be 'sock' (a socket) and 'addr' (a tuple
        containing the remote IP address and port) or just 'addr' when you want
        a new connection.""" 

        if 'sock' in kwargs:        
            self.socket = kwargs['sock']
        else:
            self.socket = None

        if 'addr' in kwargs:
            self.socket_addr = kwargs['addr']
        else:
            raise ValueError('missing argument: addr')
        
        self.connection_closed_event = Event()
        self.registration_successful_event = Event()
        self.command_events = defaultdict(Event)
        self.command_received_event = Event()

    def start(self):
        return gevent.spawn(self.run)
    
    def run(self):
        if self.socket == None:
            self.socket = socket.create_connection(self.socket_addr)
        
        self.connection = self.socket.makefile()

        self.handle_connection_made()

        while True:
            try:
                line = self.connection.readline()

                if not line:
                    break

                self.process_line(line)
            except RegistrationTimeoutError:
                self.handle_registration_timeout()

        self.connection.close()
        
        self.connection_closed_event.invoke(self)

    def process_line(self, line):
        prefix, command, params = utils.parse_irc_message(line.rstrip('\r\n'))
        
        print prefix, command, params

        command = command.upper()
                
        if not self.command_received_event.invoke(self, command=command, prefix=prefix, params=params):
            return
        
        if command in self.command_events:
            self.command_events[command].invoke(self, prefix=prefix, params=params)
        else:
            self.handle_unknown_command(prefix, command, params)

    def get_hostmask(self):
        # TODO: figure out what to do if we don't have all those vars yet
        return utils.format_hostmask( (self.nickname, self.username, self.hostname) )

    def send_message(self, command, *parameter_list, **prefix):
        params = list(parameter_list)
        
        message = ''
        
        if 'prefix' in prefix:
            message = ':' + utils.format_hostmask(prefix['prefix']) + ' '
        
        message = message + command
        
        if len(params) > 0:
            if ' ' in params[-1] and params[-1][0] != ':':
                params[-1] = ':' + params[-1]
                
            message = message + ' ' + string.join(params)
                
        self.connection.write(message + '\n')
        self.connection.flush()

    def handle_connection_made(self):
        self._registration_timeout = gevent.Timeout(60, RegistrationTimeoutError)
        self._registration_timeout.start()

    def handle_unknown_command(self, command, prefix, params):
        pass

    def register_user(self):
        self.registered = True

        self._registration_timeout.cancel()
        self._registration_timeout = None
        
        self.registration_successful_event.invoke(self)

    def handle_registration_timeout(self):
        self.close('Registration timeout detected.')

    def close(self, message=None):
        self.socket.shutdown(socket.SHUT_RDWR)
        self.socket.close()
        
    def add_command_handler(self, command, handler, priority=Event.NORMAL_PRIORITY):
        self.command_events[command].add_handler(handler, priority)
        
    def remove_command_handler(self, command, handler):
        self.command_events[command].remove_handler(handler)

class IRCClientConnection(BaseIRCConnection):
    new_connection_event = Event()

    DEFAULT_REALNAME = 'sbncng client'
    realname = DEFAULT_REALNAME

    def handle_connection_made(self):
        if not IRCClientConnection.new_connection_event.invoke(self):
            return
        
        IRCClientConnection.CommandHandlers.register_handlers(self)
        
        BaseIRCConnection.handle_connection_made(self)

        if self.attempted_nickname == None:
            raise ValueError('attempted_nickname attribute not set')
        
        if self.username == None:
            raise ValueError('username attribute not set')
        
        if self.realname == None:
            raise ValueError('realname attribute not set')
        
        if self.password != None:
            self.send_message('PASS', self.password)
            
        self.send_message('USER', self.username, '0', '*', self.realname)
        self.send_message('NICK', self.attempted_nickname)

    def close(self, message=None):
        self.send_message('QUIT', message)
        BaseIRCConnection.close(self, message)
    
    def handle_unknown_command(self, prefix, command, params):
        print "No idea how to handle this: command=", command, " - params=", params

    class CommandHandlers(object):
        def register_handlers(ircobj):
            ircobj.add_command_handler('PING', IRCClientConnection.CommandHandlers.irc_PING, Event.LOW_PRIORITY)
            ircobj.add_command_handler('001', IRCClientConnection.CommandHandlers.irc_001, Event.LOW_PRIORITY)
            ircobj.add_command_handler('NICK', IRCClientConnection.CommandHandlers.irc_NICK, Event.LOW_PRIORITY)
        
        register_handlers = staticmethod(register_handlers)
        
        def irc_PING(event, ircobj, prefix, params):
            if len(params) < 1:
                return
    
            ircobj.send_message('PONG', params[0])
            
        irc_PING = staticmethod(irc_PING)
    
        def irc_001(event, ircobj, prefix, params):
            ircobj.nickname = ircobj.attempted_nickname
            ircobj.attempted_nickname = None
    
            ircobj.register_user()
    
        irc_001 = staticmethod(irc_001)
    
        def irc_NICK(event, ircobj, prefix, params):
            if len(params) < 1 or prefix == None:
                return
            
            if prefix[0] == ircobj.nickname:
                ircobj.nickname = prefix[0]

        irc_NICK = staticmethod(irc_NICK)

class IRCServerConnection(BaseIRCConnection):
    new_connection_event = Event()

    DEFAULT_SERVERNAME = 'server.shroudbnc.info'
    servername = DEFAULT_SERVERNAME

    rpls = {
        'RPL_WELCOME': (1, 'Welcome to the Internet Relay Network %s!%s@%s'),
        'ERR_UNKNOWNCOMMAND': (421, 'Unknown command'),
        'ERR_NONICKNAMEGIVEN': (431, 'No nickname given'),
        'ERR_ERRONEUSNICKNAME': (432, 'Erroneous nickname'),
        'ERR_NEEDMOREPARAMS': (461, 'Not enough parameters.'),
        'ERR_ALREADYREGISTRED': (462, 'Unauthorized command (already registered)')
    }

    def __init__(self, **kwargs):
        BaseIRCConnection.__init__(self, **kwargs)

        self.hostname = self.socket_addr[0]

    def send_reply(self, rpl, *params, **format_args):
        nickname = self.nickname

        if nickname == None:
            nickname = '*'
        
        command = IRCServerConnection.rpls[rpl][0]
        
        try:
            command = str(int(command)).rjust(3, '0')
        except ValueError:
            pass
        
        if 'format_args' in format_args:
            text = IRCServerConnection.rpls[rpl][1] % format_args['format_args']
        else:
            text = IRCServerConnection.rpls[rpl][1]
        
        return self.send_message(command, *[nickname] + list(params) + [text], \
                                **{'prefix': IRCServerConnection.servername})

    def handle_connection_made(self):
        if not IRCServerConnection.new_connection_event.invoke(self):
            return
        
        IRCServerConnection.CommandHandlers.register_handlers(self)
        
        BaseIRCConnection.handle_connection_made(self)
                
        self.send_message('NOTICE', 'AUTH', '*** sbncng 0.1 - (c) 2011 Gunnar Beutner')
        self.send_message('NOTICE', 'AUTH', '*** Welcome to the brave new world.')

        try:
            self.send_message('NOTICE', 'AUTH', '*** Looking up your hostname')
            # TODO: need to figure out how to do IPv6 reverse lookups
            result = dns.resolve_reverse(socket.inet_aton(self.hostname))
            self.hostname = result[1]
            self.send_message('NOTICE', 'AUTH', '*** Found your hostname')
        except dns.DNSError:
            self.send_message('NOTICE', 'AUTH', '*** Couldn\'t look up your hostname, using ' + \
                             'your IP address instead (%s)' % (self.hostname))

    def close(self, message=None):
        self.send_message('ERROR', message)
        BaseIRCConnection.close(self, message)

    def register_user(self):
        assert not self.registered

        if self.nickname == None or self.username == None:
            return
        
        if self.password == None:
            self.send_message('NOTICE', 'AUTH', '*** Your client did not send a password, please ' + \
                             'use /QUOTE PASS <password> to send one now.')
            return

        if not self.authenticate_user():
            self.close('Authentication failed: Invalid user credentials.')
            return
        
        if not self.registration_successful_event.invoke(self):
            return

        BaseIRCConnection.register_user(self)
        
        self.password = None
        
        self.send_reply('RPL_WELCOME', format_args=(self.nickname, self.username, self.hostname))
        # TODO: send motd/end of motd

    def authenticate_user(self):
        return True

    def handle_unknown_command(self, prefix, command, params):
        self.send_reply('ERR_UNKNOWNCOMMAND', command)    

    class CommandHandlers(object):
        def register_handlers(ircobj):
            ircobj.add_command_handler('USER', IRCServerConnection.CommandHandlers.irc_USER, Event.LOW_PRIORITY)
            ircobj.add_command_handler('NICK', IRCServerConnection.CommandHandlers.irc_NICK, Event.LOW_PRIORITY)
            ircobj.add_command_handler('PASS', IRCServerConnection.CommandHandlers.irc_PASS, Event.LOW_PRIORITY)
            ircobj.add_command_handler('QUIT', IRCServerConnection.CommandHandlers.irc_QUIT, Event.LOW_PRIORITY)
        
        register_handlers = staticmethod(register_handlers)

        def irc_USER(event, ircobj, prefix, params):
            if len(params) < 4:
                ircobj.send_reply('ERR_NEEDMOREPARAMS', 'USER')
                return
        
            if ircobj.registered:
                ircobj.send_reply('ERR_ALREADYREGISTRED')
                return
        
            ircobj.username = params[0]
            ircobj.realname = params[3]
            
            ircobj.register_user()
        
        irc_USER = staticmethod(irc_USER)
        
        def irc_NICK(event, ircobj, source, params):
            if len(params) < 1:
                ircobj.send_reply('ERR_NONICKNAMEGIVEN', 'NICK')
                return
        
            if params[0] == ircobj.nickname:
                return
            
            if ' ' in params[0]:
                ircobj.send_reply('ERR_ERRONEUSNICKNAME', params[0])
                return
            
            if not ircobj.registered:
                ircobj.nickname = params[0]
                ircobj.register_user()
            else:
                ircobj.send_message('NICK', params[0], source=ircobj.get_hostmask())
                ircobj.nickname = params[0]
        
        irc_NICK = staticmethod(irc_NICK)
        
        def irc_PASS(event, ircobj, prefix, params):
            if len(params) < 1:
                ircobj.send_reply('ERR_NEEDMOREPARAMS', 'PASS')
                return
            
            if ircobj.registered:
                ircobj.send_reply('ERR_ALREADYREGISTRED')
                return
                
            ircobj.password = params[0]
        
            ircobj.register_user()
        
        irc_PASS = staticmethod(irc_PASS)
        
        def irc_QUIT(event, ircobj, prefix, params):
            ircobj.close('Goodbye.')
            
        irc_QUIT = staticmethod(irc_QUIT)
            
class IRCServerListener(object):
    def __init__(self, bind_address):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.bind(bind_address)
        self.socket.listen(1)
        
    def start(self):
        return gevent.spawn(self.run)
    
    def run(self):
        while True:
            sock, addr = self.socket.accept()
            print("Accepted connection from", addr)
            
            IRCServerConnection(sock=sock, addr=addr).start()
