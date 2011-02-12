import string
from collections import defaultdict
import gevent
from gevent import socket, dns
from sbnc import utils
from sbnc.event import Event
from datetime import datetime
from weakref import WeakValueDictionary

class RegistrationTimeoutError(Exception):
    pass

class _BaseConnection(object):
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

        self.registered = False
        self.attempted_nickname = None
        self.hostmask = utils.Hostmask()
        self.realname = None
        self.servername = None
        self.usermodes = ''
        self.nicks = WeakValueDictionary()
        self.channels = {}
        self.isupport = {}
        self.motd = []

        self._registration_timeout = None

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

        have_cmd_handler = command in self.command_events and self.command_events[command].handlers_count > 0

        if have_cmd_handler:
            if not self.command_events[command].invoke(self, prefix, params):
                return

        if not self.command_received_event.invoke(self, command, prefix, params):
            return

        if not have_cmd_handler:
            self.handle_unknown_command(prefix, command, params)

    def send_line(self, line):
        self.connection.write(line + '\n')
        self.connection.flush()

    def send_message(self, command, *parameter_list, **prefix):
        params = list(parameter_list)

        message = ''

        if 'prefix' in prefix and prefix['prefix'] != None:
            message = ':' + str(utils.Hostmask(prefix['prefix'])) + ' '

        message = message + command

        if len(params) > 0:
            if len(params[-1]) > 0:
                params[-1] = ':' + params[-1]

            message = message + ' ' + string.join(params)

        self.send_line(message)

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

class ConnectionFactory(object):
    def __init__(self, cls):
        self.new_connection_event = Event()
        self._cls = cls

    def create(self, **kwargs):
        ircobj = self._cls(**kwargs)

        if not self.new_connection_event.invoke(self, ircobj):
            ircobj.close()
            return None

        return ircobj

class ClientConnection(_BaseConnection):
    def __init__(self, **kwargs):
        _BaseConnection.__init__(self, **kwargs)
        
        self.reg_nickname = None
        self.reg_username = None
        self.reg_realname = None
        self.reg_password = None
        
    def handle_connection_made(self):
        ClientConnection.CommandHandlers.register_handlers(self)

        _BaseConnection.handle_connection_made(self)

        if self.reg_nickname == None:
            raise ValueError('reg_nickname attribute not set')

        if self.reg_username == None:
            raise ValueError('reg_username attribute not set')

        if self.reg_realname == None:
            raise ValueError('reg_realname attribute not set')

        if self.reg_password != None:
            self.send_message('PASS', self.reg_password)

        self.send_message('USER', self.reg_username, '0', '*', self.reg_realname)
        self.send_message('NICK', self.reg_nickname)

    def close(self, message=None):
        self.send_message('QUIT', message)
        _BaseConnection.close(self, message)

    def handle_unknown_command(self, prefix, command, params):
        print "No idea how to handle this: command=", command, " - params=", params

    class CommandHandlers(object):
        def register_handlers(ircobj):
            ircobj.command_received_event.add_handler(ClientConnection.CommandHandlers.command_received_handler)

            ircobj.add_command_handler('PING', ClientConnection.CommandHandlers.irc_PING, Event.LOW_PRIORITY)
            ircobj.add_command_handler('001', ClientConnection.CommandHandlers.irc_001, Event.LOW_PRIORITY)
            ircobj.add_command_handler('005', ClientConnection.CommandHandlers.irc_005, Event.LOW_PRIORITY)
            ircobj.add_command_handler('375', ClientConnection.CommandHandlers.irc_375, Event.LOW_PRIORITY)
            ircobj.add_command_handler('372', ClientConnection.CommandHandlers.irc_372, Event.LOW_PRIORITY)
            ircobj.add_command_handler('NICK', ClientConnection.CommandHandlers.irc_NICK, Event.LOW_PRIORITY)
            ircobj.add_command_handler('JOIN', ClientConnection.CommandHandlers.irc_JOIN, Event.LOW_PRIORITY)

        register_handlers = staticmethod(register_handlers)

        def command_received_handler(evt, ircobj, command, prefix, params):
            if ircobj.hostmask == None or prefix == None or prefix.nick != ircobj.hostmask.nick:
                return

            if ircobj.hostmask != prefix:
                ircobj.hostmask = prefix

        command_received_handler = staticmethod(command_received_handler)

        # PING :wineasy1.se.quakenet.org
        def irc_PING(evt, ircobj, prefix, params):
            if len(params) < 1:
                return

            ircobj.send_message('PONG', params[0])

            evt.stop_handlers()

        irc_PING = staticmethod(irc_PING)

        # :wineasy1.se.quakenet.org 001 shroud_ :Welcome to the QuakeNet IRC Network, shroud_
        def irc_001(evt, ircobj, prefix, params):
            ircobj.hostmask.nick = ircobj.reg_nickname

            ircobj.servername = str(prefix)

            ircobj.register_user()

        irc_001 = staticmethod(irc_001)

        # :wineasy1.se.quakenet.org 005 shroud_ WHOX WALLCHOPS WALLVOICES USERIP CPRIVMSG CNOTICE \
        # SILENCE=15 MODES=6 MAXCHANNELS=20 MAXBANS=45 NICKLEN=15 :are supported by this server
        def irc_005(evt, ircobj, prefix, params):
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

        # :wineasy1.se.quakenet.org 375 shroud_ :- wineasy1.se.quakenet.org Message of the Day - 
        def irc_375(evt, ircobj, prefix, params):
            ircobj.motd = []

        irc_375 = staticmethod(irc_375)

        # :wineasy1.se.quakenet.org 372 shroud_ :- ** [ wineasy.se.quakenet.org ] **************************************** 
        def irc_372(evt, ircobj, prefix, params):
            if len(params) < 2:
                return

            ircobj.motd.append(params[1])

        irc_372 = staticmethod(irc_372)

        # :shroud_!~shroud@p579F98A1.dip.t-dialin.net NICK :shroud__
        def irc_NICK(evt, ircobj, prefix, params):
            if len(params) < 1 or prefix == None:
                return

            if prefix[0] == ircobj.hostmask.nick:
                ircobj.hostmask.nick = prefix[0]

            # TODO: check channels/nicks list

        irc_NICK = staticmethod(irc_NICK)

        # :shroud_!~shroud@p579F98A1.dip.t-dialin.net JOIN #sbncng
        def irc_JOIN(evt, ircobj, prefix, params):
            if len(params) < 1:
                return

            nick = prefix.nick
            channel = params[0]

            if not nick in ircobj.nicks:
                nickobj = Nick(prefix)
                ircobj.nicks[nick] = nickobj
            else:
                nickobj = ircobj.nicks[nick]

            if nick == ircobj.hostmask.nick:
                channelobj = Channel(channel)
                ircobj.channels[channel] = channelobj
            else:
                channelobj = ircobj.channels[channel]

            channelobj.add_nick(nickobj)

        irc_JOIN = staticmethod(irc_JOIN)

class ServerConnection(_BaseConnection):
    DEFAULT_SERVERNAME = 'server.shroudbnc.info'

    rpls = {
        'RPL_WELCOME': (1, 'Welcome to the Internet Relay Network %s'),
        'RPL_ISUPPORT': (5, 'are supported by this server'),
        'RPL_MOTDSTART': (375, '- %s Message of the day -'),
        'RPL_MOTD': (372, '- %s'),
        'RPL_ENDMOTD': (376, 'End of MOTD command'),
        'ERR_UNKNOWNCOMMAND': (421, 'Unknown command'),
        'ERR_NOMOTD': (422, 'MOTD File is missing'),
        'ERR_NONICKNAMEGIVEN': (431, 'No nickname given'),
        'ERR_ERRONEUSNICKNAME': (432, 'Erroneous nickname'),
        'ERR_NEEDMOREPARAMS': (461, 'Not enough parameters.'),
        'ERR_ALREADYREGISTRED': (462, 'Unauthorized command (already registered)')
    }

    def __init__(self, **kwargs):
        _BaseConnection.__init__(self, **kwargs)

        self.isupport = {
            'CHANMODES': 'bIe,k,l',
            'CHANTYPES': '#&+',
            'PREFIX': '(ov)@+',
            'NAMESX': ''
        }

        self.hostmask.host = self.socket_addr[0]
        self.servername = ServerConnection.DEFAULT_SERVERNAME
        
        self._password = None

    def send_reply(self, rpl, *params, **format_args):
        nick = self.hostmask.nick

        if nick == None:
            nick = '*'

        command = ServerConnection.rpls[rpl][0]

        try:
            command = str(int(command)).rjust(3, '0')
        except ValueError:
            pass

        if 'format_args' in format_args:
            text = ServerConnection.rpls[rpl][1] % format_args['format_args']
        else:
            text = ServerConnection.rpls[rpl][1]

        return self.send_message(command, *[nick] + list(params) + [text], \
                                **{'prefix': self.servername})

    def handle_connection_made(self):
        ServerConnection.CommandHandlers.register_handlers(self)

        _BaseConnection.handle_connection_made(self)

        self.send_message('NOTICE', 'AUTH', '*** sbncng 0.1 - (c) 2011 Gunnar Beutner')
        self.send_message('NOTICE', 'AUTH', '*** Welcome to the brave new world.')

        try:
            self.send_message('NOTICE', 'AUTH', '*** Looking up your hostname')
            # TODO: need to figure out how to do IPv6 reverse lookups
            result = dns.resolve_reverse(socket.inet_aton(self.hostmask.host))
            self.hostmask.host = result[1]
            self.send_message('NOTICE', 'AUTH', '*** Found your hostname')
        except dns.DNSError:
            self.send_message('NOTICE', 'AUTH', '*** Couldn\'t look up your hostname, using ' + \
                             'your IP address instead (%s)' % (self.hostmask.host))

    def close(self, message=None):
        self.send_message('ERROR', message)
        _BaseConnection.close(self, message)

    def register_user(self):
        assert not self.registered

        if self.hostmask.nick == None or self.hostmask.user == None:
            return

        if self._password == None:
            self.send_message('NOTICE', 'AUTH', '*** Your client did not send a password, please ' + \
                             'use /QUOTE PASS <password> to send one now.')
            return

        if not self.authenticate_user():
            self.close('Authentication failed: Invalid user credentials.')
            return

        _BaseConnection.register_user(self)

        self._password = None

        self.send_reply('RPL_WELCOME', format_args=(str(self.hostmask)))

        self.process_line('VERSION')
        self.process_line('MOTD')

    def authenticate_user(self):
        return True

    def handle_unknown_command(self, prefix, command, params):
        self.send_reply('ERR_UNKNOWNCOMMAND', command)

    class CommandHandlers(object):
        def register_handlers(ircobj):
            ircobj.add_command_handler('USER', ServerConnection.CommandHandlers.irc_USER, Event.LOW_PRIORITY)
            ircobj.add_command_handler('NICK', ServerConnection.CommandHandlers.irc_NICK, Event.LOW_PRIORITY)
            ircobj.add_command_handler('PASS', ServerConnection.CommandHandlers.irc_PASS, Event.LOW_PRIORITY)
            ircobj.add_command_handler('QUIT', ServerConnection.CommandHandlers.irc_QUIT, Event.LOW_PRIORITY)
            ircobj.add_command_handler('VERSION', ServerConnection.CommandHandlers.irc_VERSION, Event.LOW_PRIORITY)
            ircobj.add_command_handler('MOTD', ServerConnection.CommandHandlers.irc_MOTD, Event.LOW_PRIORITY)

        register_handlers = staticmethod(register_handlers)

        def irc_USER(evt, ircobj, prefix, params):
            if len(params) < 4:
                ircobj.send_reply('ERR_NEEDMOREPARAMS', 'USER')
                return

            if ircobj.registered:
                ircobj.send_reply('ERR_ALREADYREGISTRED')
                return

            ircobj.hostmask.user = params[0]
            ircobj.realname = params[3]

            ircobj.register_user()

        irc_USER = staticmethod(irc_USER)

        def irc_NICK(evt, ircobj, prefix, params):
            if len(params) < 1:
                ircobj.send_reply('ERR_NONICKNAMEGIVEN', 'NICK')
                return

            if params[0] == ircobj.hostmask.nick:
                return

            if ' ' in params[0]:
                ircobj.send_reply('ERR_ERRONEUSNICKNAME', params[0])
                return

            if not ircobj.registered:
                ircobj.hostmask.nick = params[0]
                ircobj.register_user()
            else:
                ircobj.send_message('NICK', params[0], prefix=ircobj.hostmask)
                ircobj.hostmask.nick = params[0]

        irc_NICK = staticmethod(irc_NICK)

        def irc_PASS(evt, ircobj, prefix, params):
            if len(params) < 1:
                ircobj.send_reply('ERR_NEEDMOREPARAMS', 'PASS')
                return

            if ircobj.registered:
                ircobj.send_reply('ERR_ALREADYREGISTRED')
                return

            ircobj._password = params[0]

            ircobj.register_user()

        irc_PASS = staticmethod(irc_PASS)

        def irc_QUIT(evt, ircobj, prefix, params):
            ircobj.close('Goodbye.')

        irc_QUIT = staticmethod(irc_QUIT)

        def irc_VERSION(evt, ircobj, prefix, params):
            attribs = []
            length = 0

            for key in ircobj.isupport:
                value = ircobj.isupport[key]

                if len(value) > 0:
                    attrib = '%s=%s' % (key, value)
                else:
                    attrib = key

                attribs.append(attrib)
                length += len(attrib)

                if length > 300:
                    attribs = []
                    length = 0
                    ircobj.send_reply('RPL_ISUPPORT', *attribs)

            if length > 0:
                ircobj.send_reply('RPL_ISUPPORT', *attribs)

            evt.stop_handlers()

        irc_VERSION = staticmethod(irc_VERSION)

        def irc_MOTD(evt, ircobj, prefix, params):
            if len(ircobj.motd) > 0:
                ircobj.send_reply('RPL_MOTDSTART', format_args=(ircobj.servername))

                for line in ircobj.motd:
                    ircobj.send_reply('RPL_MOTD', format_args=(line))

                ircobj.send_reply('RPL_ENDMOTD')
            else:
                ircobj.send_reply('ERR_NOMOTD')
                
            evt.stop_handlers()

        irc_MOTD = staticmethod(irc_MOTD)

class ServerListener(object):
    def __init__(self, bind_address, factory):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.bind(bind_address)
        self.socket.listen(1)

        self._factory = factory

    def start(self):
        return gevent.spawn(self.run)

    def run(self):
        while True:
            sock, addr = self.socket.accept()
            print("Accepted connection from", addr)

            self._factory.create(sock=sock, addr=addr).start()

class Channel(object):
    def __init__(self, name):
        self.name = name
        self.tags = {}
        self.nicks = {}
        self.bans = []
        self.jointime = datetime.now()

        self.topic_text = None
        self.topic_time = None
        self.topic_hostmask = None

    def add_nick(self, nick):
        membership = ChannelMembership(nick, self)
        self.nicks[nick] = membership

        return membership

    def remove_nick(self, nick):
        del self.nicks[nick]

class ChannelMembership(object):
    def __init__(self, nick, channel):
        self.tags = {}
        self.nick = nick
        self.channel = channel
        self.modes = ''
        self.jointime = datetime.now()
        self.idlesince = datetime.now()

    def has_mode(self, mode):
        return mode in self.modes

    def _is_opped(self):
        return self.has_mode('o')

    opped = property(_is_opped)

    def _is_voiced(self):
        return self.has_mode('v')

    voiced = property(_is_voiced)

class Nick(object):
    def __init__(self, hostmask):
        self.hostmask = hostmask
        self.tags = {}
        self.realname = None
        self.away = False
        self.opered = False
        self.creation = datetime.now()
