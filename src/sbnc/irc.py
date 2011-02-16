from collections import defaultdict
import gevent
from gevent import socket, dns, queue
from sbnc import utils
from sbnc.event import Event
from datetime import datetime
from weakref import WeakValueDictionary

class RegistrationTimeoutError(Exception):
    pass

class QueuedLineWriter(object):
    def __init__(self, connection):
        self._connection = connection
        self._queue = queue.Queue()
    
    def start(self):
        self._thread = gevent.spawn(self._run)
    
    def _run(self):
        while True:
            line = self._queue.get()
            
            if line == False:
                break
            
            try:
                self._connection.write(line + '\n')
            except:
                pass
    
        self._connection.close()
    
    def write_line(self, line):
        self._queue.put(line)
    
    def clear(self):
        while self._queue.get(block=False) != None:
            pass
    
    def close(self):
        self._queue.put(False)

class _BaseConnection(object):
    MAX_LINELEN = 512

    def __init__(self, address, socket=None):
        """
        Base class for IRC connections.

        address: A tuple containing the remote host/IP and port
                 of the connection
        socket: An existing socket for the connection, or None
                if a new connection is to be established.
        """

	self.socket_address = address
	self.socket = socket

        self.connection_closed_event = Event()
        self.registration_event = Event()
        self.command_received_event = Event()

        self.command_events = defaultdict(Event)

        self.me = Nick(self)
        self.server = Nick(self)

        self.registered = False
        self.realname = None
        self.usermodes = ''

        self.nicks = WeakValueDictionary()
        self.channels = {}

        self.isupport = {
            'CHANMODES': 'bIe,k,l',
            'CHANTYPES': '#&+',
            'PREFIX': '(ov)@+',
            'NAMESX': ''
        }

        self.motd = []

        self.owner = None

        self._registration_timeout = None

    def start(self):
        return gevent.spawn(self._run)

    def _run(self):
        if self.socket == None:
            self.socket = socket.create_connection(self.socket_address)

        connection = self.socket.makefile('w+', 1)
        
        self._line_writer = QueuedLineWriter(connection)
        self._line_writer.start()

        try:
            self.handle_connection_made()

            while True:
                try:
                    line = connection.readline()

                    if not line:
                        break

                    self.process_line(line)
                except Exception, exc:
                    if not self.handle_exception(exc):
                        raise
        finally:
            try:
                self._line_writer.close()
            except:
                pass

            self.connection_closed_event.invoke(self)

    def close(self, message=None):
        self._line_writer.close()

    def handle_exception(self, exc):
        if exc == self._registration_timeout:
            self._registration_timeout.cancel()
            self.handle_registration_timeout()
            return True

    def get_nick(self, hostmask):
        if hostmask == None:
            return None

        hostmask_dict = utils.parse_hostmask(hostmask)
        nick = hostmask_dict['nick']
    
        nickobj = None
    
        if nick == self.me.nick:
            nickobj = self.me
        elif nick == self.server.nick:
            nickobj = self.server
        elif nick in self.nicks:
            nickobj = self.nicks[nick]
        else:
            nickobj = Nick(self, hostmask_dict)
            self.nicks[nick] = nickobj
            
        nickobj.update_hostmask(hostmask_dict)

        return nickobj

    def process_line(self, line):
        prefix, command, params = utils.parse_irc_message(line.rstrip('\r\n'))
        nickobj = self.get_nick(prefix)

        print nickobj, command, params

        command = command.upper()

        have_cmd_handler = command in self.command_events and \
            self.command_events[command].handlers_count > 0

        if have_cmd_handler:
            if not self.command_events[command].invoke(self, nickobj, params):
                return

        if not self.command_received_event.invoke(self, command, nickobj, params):
            return

        if not have_cmd_handler:
            self.handle_unknown_command(nickobj, command, params)

    def send_line(self, line):
        self._line_writer.write_line(line)

    def send_message(self, command, *parameter_list, **prefix):
        self.send_line(utils.format_irc_message(command, *parameter_list, **prefix))

    def handle_connection_made(self):
        self._registration_timeout = gevent.Timeout.start_new(60, RegistrationTimeoutError)

    def handle_unknown_command(self, command, nickobj, params):
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

class IRCConnection(_BaseConnection):
    def __init__(self, address, socket=None):
        _BaseConnection.__init__(self, address, socket)
        
        self.reg_nickname = None
        self.reg_username = None
        self.reg_realname = None
        self.reg_password = None
        
    def handle_connection_made(self):
        IRCConnection.CommandHandlers.register_handlers(self)

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

    def handle_unknown_command(self, nickobj, command, params):
        print "No idea how to handle this: command=", command, " - params=", params

    class CommandHandlers(object):
        def register_handlers(ircobj):
            ircobj.add_command_handler('PING', IRCConnection.CommandHandlers.irc_PING, Event.LOW_PRIORITY)
            ircobj.add_command_handler('ERROR', IRCConnection.CommandHandlers.irc_ERROR, Event.LOW_PRIORITY)
            ircobj.add_command_handler('001', IRCConnection.CommandHandlers.irc_001, Event.LOW_PRIORITY)
            ircobj.add_command_handler('005', IRCConnection.CommandHandlers.irc_005, Event.LOW_PRIORITY)
            ircobj.add_command_handler('375', IRCConnection.CommandHandlers.irc_375, Event.LOW_PRIORITY)
            ircobj.add_command_handler('372', IRCConnection.CommandHandlers.irc_372, Event.LOW_PRIORITY)
            ircobj.add_command_handler('NICK', IRCConnection.CommandHandlers.irc_NICK, Event.LOW_PRIORITY)
            ircobj.add_command_handler('JOIN', IRCConnection.CommandHandlers.irc_JOIN, Event.LOW_PRIORITY)
            ircobj.add_command_handler('PART', IRCConnection.CommandHandlers.irc_PART, Event.LOW_PRIORITY)
            ircobj.add_command_handler('KICK', IRCConnection.CommandHandlers.irc_KICK, Event.LOW_PRIORITY)
            ircobj.add_command_handler('QUIT', IRCConnection.CommandHandlers.irc_QUIT, Event.LOW_PRIORITY)
            ircobj.add_command_handler('353', IRCConnection.CommandHandlers.irc_353, Event.LOW_PRIORITY)
            ircobj.add_command_handler('366', IRCConnection.CommandHandlers.irc_366, Event.LOW_PRIORITY)
            ircobj.add_command_handler('433', IRCConnection.CommandHandlers.irc_433, Event.LOW_PRIORITY)

        register_handlers = staticmethod(register_handlers)

        # PING :wineasy1.se.quakenet.org
        def irc_PING(evt, ircobj, nickobj, params):
            if len(params) < 1:
                return

            ircobj.send_message('PONG', params[0])

            evt.stop_handlers()

        irc_PING = staticmethod(irc_PING)

        # ERROR :Registration timeout.
        def irc_ERROR(evt, ircobj, nickobj, params):
            ircobj.close()
            
            evt.stop_handlers()
            
        irc_ERROR = staticmethod(irc_ERROR)

        # :wineasy1.se.quakenet.org 001 shroud_ :Welcome to the QuakeNet IRC Network, shroud_
        def irc_001(evt, ircobj, nickobj, params):
            ircobj.me.nick = ircobj.reg_nickname

            ircobj.server = nickobj

            ircobj.register_user()

        irc_001 = staticmethod(irc_001)

        # :wineasy1.se.quakenet.org 005 shroud_ WHOX WALLCHOPS WALLVOICES USERIP CPRIVMSG CNOTICE \
        # SILENCE=15 MODES=6 MAXCHANNELS=20 MAXBANS=45 NICKLEN=15 :are supported by this server
        def irc_005(evt, ircobj, nickobj, params):
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
        def irc_375(evt, ircobj, nickobj, params):
            ircobj.motd = []

        irc_375 = staticmethod(irc_375)

        # :wineasy1.se.quakenet.org 372 shroud_ :- ** [ wineasy.se.quakenet.org ] **************************************** 
        def irc_372(evt, ircobj, nickobj, params):
            if len(params) < 2:
                return

            motdline = params[1]
            
            if motdline[:2] == '- ':
                motdline = motdline[2:]
            
            ircobj.motd.append(params[1])

        irc_372 = staticmethod(irc_372)

        # :shroud_!~shroud@p579F98A1.dip.t-dialin.net NICK :shroud__
        def irc_NICK(evt, ircobj, nickobj, params):
            if len(params) < 1 or nickobj == None:
                return

            oldnick = nickobj.nick
            newnick = params[0]

            if newnick == ircobj.me.nick:
                ircobj.me.nick = newnick

            if oldnick in ircobj.nicks:
                nickobj = ircobj.nicks[oldnick]
                nickobj.nick = newnick
                
                del ircobj.nicks[oldnick]
                ircobj.nicks[newnick] = nickobj
                
        irc_NICK = staticmethod(irc_NICK)

        # :shroud_!~shroud@p579F98A1.dip.t-dialin.net JOIN #sbncng
        def irc_JOIN(evt, ircobj, nickobj, params):
            if len(params) < 1:
                return

            channel = params[0]

            if nickobj == ircobj.me:
                channelobj = Channel(ircobj, channel)
                ircobj.channels[channel] = channelobj
            else:
                if not channel in ircobj.channels:
                    return
                
                channelobj = ircobj.channels[channel]

            channelobj.add_nick(nickobj)

        irc_JOIN = staticmethod(irc_JOIN)

        # :shroud_!~shroud@p579F98A1.dip.t-dialin.net PART #sbncng
        def irc_PART(evt, ircobj, nickobj, params):
            if len(params) < 1:
                return
        
            channel = params[0]
            
            if not channel in ircobj.channels:
                return

            if nickobj == ircobj.me:
                del ircobj.channels[channel]
            else:            
                channelobj = ircobj.channels[channel]
                
                if not nickobj in channelobj.nicks:
                    return
                
                channelobj.remove_nick(nickobj)

        irc_PART = staticmethod(irc_PART)
        
        # :shroud_!~shroud@p579F98A1.dip.t-dialin.net KICK #sbncng sbncng :test
        def irc_KICK(evt, ircobj, nickobj, params):
            if len(params) < 2:
                return
            
            channel = params[0]
            victim = params[1]
                        
            if not channel in ircobj.channels:
                return
            
            victimobj = ircobj.get_nick(victim)

            if victimobj == ircobj.me:
                del ircobj.channels[channel]
            else:
                channelobj = ircobj.channels[channel]
                
                if not nickobj in channelobj.nicks:
                    return
                
                channelobj.remove_nick(nickobj)
            
        irc_KICK = staticmethod(irc_KICK)

        # :shroud_!~shroud@p579F98A1.dip.t-dialin.net QUIT :test
        def irc_QUIT(evt, ircobj, nickobj, params):
            channels = list(nickobj.channels)
            
            for channel in channels:
                channel.remove_nick(nickobj)
            
        irc_QUIT = staticmethod(irc_QUIT)
        
        # :server.shroudbnc.info 353 sbncng = #sbncng :sbncng @shroud
        def irc_353(evt, ircobj, nickobj, params):
            if len(params) < 4:
                return
            
            channel = params[2]
            
            if not channel in ircobj.channels:
                return
            
            channelobj = ircobj.channels[channel]
            
            tokens = params[3].split(' ')
            
            for token in tokens:
                nick = token
                modes = ''
                
                while len(nick) > 0:
                    mode = utils.prefix_to_mode(ircobj.isupport['PREFIX'], nick[0])
                    
                    if mode == None:
                        break
                    
                    nick = nick[1:]
                    modes += mode
                
                nickobj = ircobj.get_nick(nick)
                
                if nickobj in channelobj.nicks:
                    membership = channelobj.nicks[nickobj]
                else:
                    membership = channelobj.add_nick(nickobj)

                membership.modes = modes
                
                print nick, modes
        
        irc_353 = staticmethod(irc_353)
        
        # :server.shroudbnc.info 366 sbncng #sbncng :End of /NAMES list.
        def irc_366(evt, ircobj, nickobj, params):
            if len(params) < 2:
                return
            
            channel = params[1]
            
            if not channel in ircobj.channels:
                return
            
            channelobj = ircobj.channels[channel]

            channelobj.has_names = True
            
        irc_366 = staticmethod(irc_366)

        # :underworld2.no.quakenet.org 433 * shroud :Nickname is already in use.
        def irc_433(evt, ircobj, nickobj, params):
            if len(params) < 2 or ircobj.registered:
                return
            
            newnick = params[1] + '_'
            
            ircobj.reg_nickname = newnick
                
            ircobj.send_message('NICK', newnick)

        irc_433 = staticmethod(irc_433)

class ClientConnection(_BaseConnection):
    DEFAULT_SERVERNAME = 'server.shroudbnc.info'

    rpls = {
        'RPL_WELCOME': (1, 'Welcome to the Internet Relay Network %s'),
        'RPL_ISUPPORT': (5, 'are supported by this server'),
        'RPL_NAMREPLY': (353, '%s'),
        'RPL_ENDOFNAMES': (366, 'End of NAMES list'),
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

    def __init__(self, address, socket):
        _BaseConnection.__init__(self, address, socket)

        self.me.host = self.socket_address[0]
        self.server.nick = ClientConnection.DEFAULT_SERVERNAME
        
        self.authentication_event = Event()
        
        self._password = None

    def send_reply(self, rpl, *params, **format_args):
        nick = self.me.nick

        if nick == None:
            nick = '*'

        command = ClientConnection.rpls[rpl][0]

        try:
            command = str(int(command)).rjust(3, '0')
        except ValueError:
            pass

        if 'format_args' in format_args:
            text = ClientConnection.rpls[rpl][1] % format_args['format_args']
        else:
            text = ClientConnection.rpls[rpl][1]

        return self.send_message(command, *[nick] + list(params) + [text], \
                                **{'prefix': self.server})

    def handle_connection_made(self):
        ClientConnection.CommandHandlers.register_handlers(self)

        _BaseConnection.handle_connection_made(self)

        self.send_message('NOTICE', 'AUTH', '*** sbncng 0.1 - (c) 2011 Gunnar Beutner')
        self.send_message('NOTICE', 'AUTH', '*** Welcome to the brave new world.')

        try:
            self.send_message('NOTICE', 'AUTH', '*** Looking up your hostname')
            # TODO: need to figure out how to do IPv6 reverse lookups
            result = dns.resolve_reverse(socket.inet_aton(self.me.host))
            self.me.host = result[1]
            self.send_message('NOTICE', 'AUTH', '*** Found your hostname (%s)' % (self.me.host))
        except dns.DNSError:
            self.send_message('NOTICE', 'AUTH', '*** Couldn\'t look up your hostname, using ' + \
                             'your IP address instead (%s)' % (self.me.host))

    def close(self, message=None):
        self.send_message('ERROR', message)
        _BaseConnection.close(self, message)

    def register_user(self):
        assert not self.registered

        if self.me.nick == None or self.me.user == None:
            return

        if self._password == None:
            self.send_message('NOTICE', 'AUTH', '*** Your client did not send a password, please ' + \
                             'use /QUOTE PASS <password> to send one now.')
            return

        if self.authentication_event.handlers_count > 0:
            self.authentication_event.invoke(self, self.me.user, self._password)
            
            if not self.owner:
                self.close('Authentication failed: Invalid user credentials.')
                return

        _BaseConnection.register_user(self)

        self._password = None

        self.send_reply('RPL_WELCOME', format_args=(str(self.me)))
        
        # TODO: missing support for RPL_YOURHOST, RPL_CREATED and RPL_MYINFO

        self.process_line('VERSION')
        self.process_line('MOTD')

    def handle_unknown_command(self, nickobj, command, params):
        self.send_reply('ERR_UNKNOWNCOMMAND', command)

    class CommandHandlers(object):
        def register_handlers(ircobj):
            ircobj.add_command_handler('USER', ClientConnection.CommandHandlers.irc_USER, Event.LOW_PRIORITY)
            ircobj.add_command_handler('NICK', ClientConnection.CommandHandlers.irc_NICK, Event.LOW_PRIORITY)
            ircobj.add_command_handler('PASS', ClientConnection.CommandHandlers.irc_PASS, Event.LOW_PRIORITY)
            ircobj.add_command_handler('QUIT', ClientConnection.CommandHandlers.irc_QUIT, Event.LOW_PRIORITY)
            ircobj.add_command_handler('VERSION', ClientConnection.CommandHandlers.irc_VERSION, Event.LOW_PRIORITY)
            ircobj.add_command_handler('MOTD', ClientConnection.CommandHandlers.irc_MOTD, Event.LOW_PRIORITY)
            ircobj.add_command_handler('NAMES', ClientConnection.CommandHandlers.irc_NAMES, Event.LOW_PRIORITY)

        register_handlers = staticmethod(register_handlers)

        # USER shroud * 0 :Gunnar Beutner
        def irc_USER(evt, ircobj, nickobj, params):
            if len(params) < 4:
                ircobj.send_reply('ERR_NEEDMOREPARAMS', 'USER')
                return

            if ircobj.registered:
                ircobj.send_reply('ERR_ALREADYREGISTRED')
                return

            ircobj.me.user = params[0]
            ircobj.realname = params[3]

            ircobj.register_user()

        irc_USER = staticmethod(irc_USER)

        # NICK shroud_
        def irc_NICK(evt, ircobj, nickobj, params):
            if len(params) < 1:
                ircobj.send_reply('ERR_NONICKNAMEGIVEN', 'NICK')
                return

            nick = params[0]

            if nick == ircobj.me.nick:
                return

            if ' ' in nick:
                ircobj.send_reply('ERR_ERRONEUSNICKNAME', nick)
                return

            if not ircobj.registered:
                ircobj.me.nick = nick
                ircobj.register_user()
            else:
                ircobj.send_message('NICK', nick, prefix=ircobj.me)
                ircobj.me.nick = nick

        irc_NICK = staticmethod(irc_NICK)

        # PASS topsecret
        def irc_PASS(evt, ircobj, nickobj, params):
            if len(params) < 1:
                ircobj.send_reply('ERR_NEEDMOREPARAMS', 'PASS')
                return

            if ircobj.registered:
                ircobj.send_reply('ERR_ALREADYREGISTRED')
                return

            ircobj._password = params[0]

            ircobj.register_user()

        irc_PASS = staticmethod(irc_PASS)

        def irc_QUIT(evt, ircobj, nickobj, params):
            ircobj.close('Goodbye.')

        irc_QUIT = staticmethod(irc_QUIT)

        # VERSION
        def irc_VERSION(evt, ircobj, nickobj, params):
            if len(params) > 0:
                return
            
            # TODO: missing support for RPL_VERSION
            
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

        # MOTD
        def irc_MOTD(evt, ircobj, nickobj, params):
            if len(ircobj.motd) > 0:
                ircobj.send_reply('RPL_MOTDSTART', format_args=(ircobj.server))

                for line in ircobj.motd:
                    ircobj.send_reply('RPL_MOTD', format_args=(line))

                ircobj.send_reply('RPL_ENDMOTD')
            else:
                ircobj.send_reply('ERR_NOMOTD')
                
            evt.stop_handlers()

        irc_MOTD = staticmethod(irc_MOTD)
        
        # NAMES #channel
        def irc_NAMES(evt, ircobj, nickobj, params):
            if len(params) != 1 or ',' in params[0]:
                return
            
            channel = params[0]
            
            if channel not in ircobj.channels:
                return
            
            channelobj = ircobj.channels[channel]
            
            if not channelobj.has_names:
                return
            
            if channelobj.has_modes and 's' in channelobj.modes:
                chantype = '@'
            elif channelobj.has_modes and 'p' in channelobj.modes:
                chantype = '*'
            else:
                chantype = '='
            
            nicklist = []
            length = 0
            
            for nickobj in channelobj.nicks:
                membership = channelobj.nicks[nickobj]
                
                length += len(nickobj.nick)
                
                prefixes = ''
                
                for mode in membership.modes:
                    prefix = utils.mode_to_prefix(ircobj.isupport['PREFIX'], mode)
                    
                    if prefix != None:
                        prefixes += prefix
                
                nicklist.append(prefixes + nickobj.nick)
                
                if length > 300:
                    ircobj.send_reply('RPL_NAMREPLY', chantype, channel, format_args=(' '.join(nicklist)))
                    nicklist = []
                    length = 0
            
            if length > 0:
                ircobj.send_reply('RPL_NAMREPLY', chantype, channel, format_args=(' '.join(nicklist)))

            ircobj.send_reply('RPL_ENDOFNAMES', channel, prefix=ircobj.server)
            
            evt.stop_handlers()
            
        irc_NAMES = staticmethod(irc_NAMES)

class ClientListener(object):
    def __init__(self, bind_address, factory):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind(bind_address)
        self.socket.listen(1)

        self._factory = factory

    def start(self):
        return gevent.spawn(self.run)

    def run(self):
        while True:
            sock, addr = self.socket.accept()
            print("Accepted connection from", addr)

            self._factory.create(socket=sock, address=addr).start()

class Channel(object):
    def __init__(self, ircobj, name):
        self._ircobj = ircobj
        
        self.name = name
        self.tags = {}
        self.nicks = {}
        self.bans = []
        self.jointime = datetime.now()

        self.topic_text = None
        self.topic_time = None
        self.topic_hostmask = None
        
        self.has_names = False
        self.has_topic = False
        self.has_bans = False
        self.has_modes = False

    def add_nick(self, nickobj):
        membership = ChannelMembership(self, nickobj)
        self.nicks[nickobj] = membership

        return membership

    def remove_nick(self, nickobj):
        del self.nicks[nickobj]

class ChannelMembership(object):
    def __init__(self, channel, nick):
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
    def __init__(self, ircobj, hostmask=None):
        self._ircobj = ircobj
    
        self.tags = {}
        self.realname = None
        self.away = False
        self.opered = False
        self.creation = datetime.now()
        
        hostmask_dict = utils.parse_hostmask(hostmask)
        
        self.nick = hostmask_dict['nick']
        self.user = hostmask_dict['user']
        self.host = hostmask_dict['host']

    def __str__(self):
        if self.user == None or self.host == None:
            return str(self.nick)
        else:
            return '%s!%s@%s' % (self.nick, self.user, self.host)

    def __eq__(self, other):
        if other == None:
            return False

        return (self.nick == other.nick) and \
               (self.user == other.user) and \
               (self.host == other.host)
               
    def __ne__(self, other):
        return not self.__eq__(other)

    def update_hostmask(self, hostmask_dict):
        if hostmask_dict['user'] != None and self.user != hostmask_dict['user']:
            self.user = hostmask_dict['user']
            
        if hostmask_dict['host'] != None and self.host != hostmask_dict['host']:
            self.host = hostmask_dict['host']

    def get_channels(self):
        for channel in self._ircobj.channels:
            channelobj = self._ircobj.channels[channel]
            
            if self in channelobj.nicks:
                yield channelobj

        raise StopIteration
    
    channels = property(get_channels)
