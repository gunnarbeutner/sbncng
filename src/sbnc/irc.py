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
    nickname = None
    username = None
    password = None
    hostname = None
    realname = None
    
    rpls = {
        'RPL_WELCOME': (1, 'Welcome to the Internet Relay Network %s!%s@%s'),
        'ERR_UNKNOWNCOMMAND': (421, 'Unknown command'),
        'ERR_NONICKNAMEGIVEN': (431, 'No nickname given'),
        'ERR_ERRONEUSNICKNAME': (432, 'Erroneous nickname'),
        'ERR_NEEDMOREPARAMS': (461, 'Not enough parameters.'),
        'ERR_ALREADYREGISTRED': (462, 'Unauthorized command (already registered)')
    }
    
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
                
                prefix, command, params = utils.parse_irc_message(line.rstrip('\r\n'))
                
                print prefix, command, params
                
                self.handle_command(command, prefix, params)
            
            except RegistrationTimeoutError:
                self.handle_registration_timeout()

        self.connection.close()
        
        self.connection_closed_event.invoke(self)

    def get_hostmask(self):
        # TODO: figure out what to do if we don't have all those vars yet
        return "%s!%s@%s" % (self.nickname, self.username, self.hostname)

    def send_message(self, command, *parameter_list, **prefix):
        params = list(parameter_list)
        
        message = ''
        
        if 'prefix' in prefix:
            message = ':' + prefix['prefix'] + ' '
        
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

    def handle_command(self, command, prefix, params):
        command = command.upper()
        
        if not self.command_received_event.invoke(self, command=command, prefix=prefix, params=params):
            return
        
        if command in self.command_events:
            if not self.command_events[command].invoke(self, prefix=prefix, params=params):
                return
        
        try:
            handler = getattr(self, 'irc_' + command)
        except AttributeError:
            handler = None
        
        if handler:
            handler(prefix, params)
        else:
            self.irc_unknown(prefix, command, params)

    def register_user(self):
        self.registered = True

        self._registration_timeout.cancel()
        self._registration_timeout = None

    def handle_registration_timeout(self):
        self.close('Registration timeout detected.')

    def close(self, message=None):
        self.socket.shutdown(socket.SHUT_RDWR)
        self.socket.close()

class IRCClientConnection(BaseIRCConnection):
    connection_made_event = Event()

    DEFAULT_REALNAME = 'sbncng client'
    realname = DEFAULT_REALNAME

    def handle_connection_made(self):
        if not IRCClientConnection.connection_made_event.invoke(self):
            return
        
        BaseIRCConnection.handle_connection_made(self)

        if self.nickname == None:
            raise ValueError('nickname attribute not set')
        
        if self.username == None:
            raise ValueError('username attribute not set')
        
        if self.realname == None:
            raise ValueError('realname attribute not set')
        
        if self.password != None:
            self.send_message('PASS', self.password)
            
        self.send_message('USER', self.username, '0', '*', self.realname)
        self.send_message('NICK', self.nickname)

    def close(self, message=None):
        self.send_message('QUIT', message)
        BaseIRCConnection.close(self, message)
        
    def irc_PING(self, prefix, params):
        if len(params) < 1:
            return

        self.send_message('PONG', params[0])

    def irc_001(self, prefix, params):
        self.register_user()

    def irc_unknown(self, prefix, command, params):
        print "No idea how to handle this: command=", command, " - params=", params

class IRCServerConnection(BaseIRCConnection):
    connection_made_event = Event()

    DEFAULT_SERVERNAME = 'server.shroudbnc.info'
    servername = DEFAULT_SERVERNAME

    def __init__(self, **kwargs):
        BaseIRCConnection.__init__(self, **kwargs)

        self.hostname = self.socket_addr[0]

    def send_reply(self, rpl, *params, **format_args):
        nickname = self.nickname

        if nickname == None:
            nickname = '*'
        
        command = BaseIRCConnection.rpls[rpl][0]
        
        try:
            command = str(int(command)).rjust(3, '0')
        except ValueError:
            pass
        
        if 'format_args' in format_args:
            text = BaseIRCConnection.rpls[rpl][1] % format_args['format_args']
        else:
            text = BaseIRCConnection.rpls[rpl][1]
        
        return self.send_message(command, *[nickname] + list(params) + [text], \
                                **{'prefix': IRCServerConnection.servername})

    def handle_connection_made(self):
        if not IRCServerConnection.connection_made_event.invoke(self):
            return
        
        BaseIRCConnection.handle_connection_made(self)
                
        self.send_message('NOTICE', 'AUTH', '*** sbncng 0.1 - (c) 2011 Gunnar Beutner')
        self.send_message('NOTICE', 'AUTH', '*** Welcome to the brave new world.')

        try:
            self.send_message('NOTICE', 'AUTH', '*** Looking up your hostname')
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

    def irc_USER(self, prefix, params):
        if len(params) < 4:
            self.send_reply('ERR_NEEDMOREPARAMS', 'USER')
            return

        if self.registered:
            self.send_reply('ERR_ALREADYREGISTRED')
            return

        self.username = params[0]
        self.realname = params[3]
        
        self.register_user()
    
    def irc_unknown(self, prefix, command, params):
        self.send_reply('ERR_UNKNOWNCOMMAND', command)
    
    def irc_NICK(self, prefix, params):
        if len(params) < 1:
            self.send_reply('ERR_NONICKNAMEGIVEN', 'NICK')
            return

        if params[0] == self.nickname:
            return
        
        if ' ' in params[0]:
            self.send_reply('ERR_ERRONEUSNICKNAME', params[0])
            return
        
        if not self.registered:
            self.nickname = params[0]
            self.register_user()
        else:
            self.send_message('NICK', params[0], prefix=self.get_hostmask())
            self.nickname = params[0]

    def irc_PASS(self, prefix, params):
        if len(params) < 1:
            self.send_reply('ERR_NEEDMOREPARAMS', 'PASS')
            return
        
        if self.registered:
            self.send_reply('ERR_ALREADYREGISTRED')
            return
            
        self.password = params[0]

        self.register_user()

    def irc_QUIT(self, prefix, params):
        self.close('Goodbye.')

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
