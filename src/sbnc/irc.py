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
    servername = None
    usermodes = ''
    channels = {}
    isupport = {}
        
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
        self.registration_event = Event()
        self.command_received_event = Event()

        self.command_events = defaultdict(Event)

    def start(self):
        return gevent.spawn(self._run)
    
    def _run(self):
        if self.socket == None:
            self.socket = socket.create_connection(self.socket_addr)
        
        self.connection = self.socket.makefile()

        try:
            self.handle_connection_made()
    
            while True:
                try:
                    line = self.connection.readline()
    
                    if not line:
                        break
    
                    self.process_line(line)
                except Exception, exc:
                    if not self.handle_exception(exc):
                        raise
    
            self.connection.close()
        finally:    
            self.connection_closed_event.invoke(self)

    def close(self, message=None):
        self.connection.flush()
        self.socket.shutdown(socket.SHUT_RDWR)
        self.socket.close()

    def handle_exception(self, exc):
        if isinstance(exc, RegistrationTimeoutError):
            self.handle_registration_timeout()
            return True

    def process_line(self, line):
        prefix, command, params = utils.parse_irc_message(line.rstrip('\r\n'))
        
        print prefix, command, params

        command = command.upper()
                
        if not self.command_received_event.invoke(self, command=command, prefix=prefix, params=params):
            return
        
        if command in self.command_events and self.command_events[command].handlers_count > 0:
            self.command_events[command].invoke(self, prefix=prefix, params=params)
        else:
            self.handle_unknown_command(prefix, command, params)

    def send_line(self, line):
        self.connection.write(line + '\n')
        self.connection.flush()

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
             
        self.send_line(message)   

    def get_hostmask(self):
        # TODO: figure out what to do if we don't have all those vars yet
        return utils.format_hostmask( (self.nickname, self.username, self.hostname) )

    def handle_connection_made(self):
        self._registration_timeout = gevent.Timeout.start_new(60, RegistrationTimeoutError)

    def handle_unknown_command(self, command, prefix, params):
        pass

    def register_user(self):
        self.registered = True

        self._registration_timeout.cancel()
        self._registration_timeout = None
        
        self.registration_event.invoke(self)

    def handle_registration_timeout(self):
        self.close('Registration timeout detected.')
        
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
            ircobj.add_command_handler('005', IRCClientConnection.CommandHandlers.irc_005, Event.LOW_PRIORITY)
            ircobj.add_command_handler('NICK', IRCClientConnection.CommandHandlers.irc_NICK, Event.LOW_PRIORITY)
        
        register_handlers = staticmethod(register_handlers)
        
        # PING :wineasy1.se.quakenet.org
        def irc_PING(event, ircobj, prefix, params):
            if len(params) < 1:
                return
    
            ircobj.send_message('PONG', params[0])
            
        irc_PING = staticmethod(irc_PING)
    
        # :wineasy1.se.quakenet.org 001 shroud_ :Welcome to the QuakeNet IRC Network, shroud_
        def irc_001(event, ircobj, prefix, params):
            ircobj.nickname = ircobj.attempted_nickname
            ircobj.attempted_nickname = None
            
            ircobj.servername = utils.format_hostmask(prefix)
    
            ircobj.register_user()
    
        irc_001 = staticmethod(irc_001)
    
        # :wineasy1.se.quakenet.org 005 shroud_ WHOX WALLCHOPS WALLVOICES USERIP CPRIVMSG CNOTICE \
        # SILENCE=15 MODES=6 MAXCHANNELS=20 MAXBANS=45 NICKLEN=15 :are supported by this server
        def irc_005(event, ircobj, prefix, params):
            if len(params) < 3:
                return
            
            attribs = params[1:-1]
            
            for attrib in attribs:
                tokens = attrib.split('=', 2)
                key = tokens[0]
                
                if len(tokens) > 1:
                    value = tokens[1]
                else:
                    value = ''
                    
                ircobj.isupport[key] = value
                
            print attribs
    
        irc_005 = staticmethod(irc_005)
        
        # :shroud_!~shroud@p579F98A1.dip.t-dialin.net NICK :shroud__
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
        'RPL_ISUPPORT': (5, '%s :are supported by this server'),
        'ERR_UNKNOWNCOMMAND': (421, 'Unknown command'),
        'ERR_NONICKNAMEGIVEN': (431, 'No nickname given'),
        'ERR_ERRONEUSNICKNAME': (432, 'Erroneous nickname'),
        'ERR_NEEDMOREPARAMS': (461, 'Not enough parameters.'),
        'ERR_ALREADYREGISTRED': (462, 'Unauthorized command (already registered)')
    }

    def __init__(self, **kwargs):
        BaseIRCConnection.__init__(self, **kwargs)

        self.isupport = {
            'CHANMODES': 'bIe,k,l',
            'CHANTYPES': '#&+',
            'PREFIX': '(ov)@+',
            'NAMESX': ''
        }

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
        
        if not self.registration_event.invoke(self):
            return

        BaseIRCConnection.register_user(self)
        
        self.password = None
        
        self.send_reply('RPL_WELCOME', format_args=(self.nickname, self.username, self.hostname))
        
        attribs = []
        length = 0
        
        for key in self.isupport:
            value = self.isupport[key]
            
            if len(value) > 0:
                attrib = '%s=%s' % (key, value)
            else:
                attrib = key
                
            attribs.append(attrib)
            length += len(attrib)
            
            if length > 300:
                attribs = []
                length = 0
                self.send_reply('RPL_ISUPPORT', format_args=(' '.join(attribs)))
                
        if length > 0:
            self.send_reply('RPL_ISUPPORT', format_args=(' '.join(attribs)))
        
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
        
        def irc_NICK(event, ircobj, prefix, params):
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
