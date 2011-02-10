import string
import gevent
from collections import defaultdict
from gevent import socket, dns
from sbnc import utils
from sbnc.event import Event

class RegistrationTimeoutError(Exception):
    pass

class ClientConnection(object):
    servername = 'server.shroudbnc.info'
    connection_made_event = Event()

    rpls = {
        'RPL_WELCOME': (1, 'Welcome to the Internet Relay Network %s!%s@%s'),
        'ERR_UNKNOWNCOMMAND': (421, 'Unknown command'),
        'ERR_NONICKNAMEGIVEN': (431, 'No nickname given'),
        'ERR_ERRONEUSNICKNAME': (432, 'Erroneous nickname'),
        'ERR_NEEDMOREPARAMS': (461, 'Not enough parameters.'),
        'ERR_ALREADYREGISTRED': (462, 'Unauthorized command (already registered)')
    }

    def __init__(self, conn, addr):
        self.socket = conn
        self.socket_addr = addr

        self.registered = False
        self.nickname = None
        self.username = None
        self.password = None
        self.hostname = addr[0]
        self.realname = None
                
        self._registration_timeout = None
        
        self.connection_closed_event = Event()
        self.registration_successful_event = Event()
        self.command_events = defaultdict(Event)
        self.command_received_event = Event()
        
    def start(self):
        return gevent.spawn(self.run)
    
    def run(self):
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
                self.send_error('Registration timeout. Please reconnect and log in.')

        self.connection.close()
        
        self.connection_closed_event.invoke(self)
        
    def get_hostmask(self):
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

    def send_reply(self, rpl, *params, **format_args):
        nickname = self.nickname

        if nickname == None:
            nickname = '*'
        
        command = ClientConnection.rpls[rpl][0]
        
        try:
            command = str(int(command)).rjust(3, '0')
        except ValueError:
            pass
        
        if 'format_args' in format_args:
            text = ClientConnection.rpls[rpl][1] % format_args['format_args']
        else:
            text = ClientConnection.rpls[rpl][1]
        
        return self.send_message(command, *[nickname] + list(params) + [text], \
                                **{'prefix': ClientConnection.servername})

    def send_error(self, message):
        self.send_message('ERROR', message)

        self.socket.shutdown(socket.SHUT_RDWR)
        self.socket.close()

    def handle_connection_made(self):
        if not ClientConnection.connection_made_event.invoke(self):
            return
        
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

    def try_register_user(self):
        assert not self.registered

        if self.nickname == None or self.username == None:
            return
        
        if self.password == None:
            self.send_message('NOTICE', 'AUTH', '*** Your client did not send a password, please ' + \
                             'use /QUOTE PASS <password> to send one now.')
            return

        if not self.authenticate_user():
            return
        
        if not self.registration_successful_event.invoke(self):
            return
        
        self.registered = True
        self.password = None
        
        self._registration_timeout.cancel()
        self._registration_timeout = None

        self.send_reply('RPL_WELCOME', format_args=(self.nickname, self.username, self.hostname))

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
        
        self.try_register_user()
    
    def irc_unknown(self, prefix, command, params):
        self.send_reply('ERR_UNKNOWNCOMMAND', command, prefix=ClientConnection.servername)
    
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
            self.try_register_user()
            
            # TODO: send 001/motd, etc.
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

        self.try_register_user()

    def irc_QUIT(self, prefix, params):
        self.send_error('Goodbye.')

class ClientListener(object):
    def __init__(self, bind_address):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.bind(bind_address)
        self.socket.listen(1)
        
    def start(self):
        return gevent.spawn(self.run)
    
    def run(self):
        while True:
            conn, addr = self.socket.accept()
            print("Accepted connection from", addr)
            
            ClientConnection(conn, addr).start()
