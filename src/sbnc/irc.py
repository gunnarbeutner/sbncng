# sbncng - an object-oriented framework for IRC
# Copyright (C) 2011 Gunnar Beutner
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA  02111-1307, USA.

import sys
import time
from copy import copy
from datetime import datetime
from weakref import WeakValueDictionary
import gevent
from gevent import socket, dns, queue
from sbnc import utils
from sbnc.event import Event, match_source, match_param
from sbnc.timer import Timer

class QueuedLineWriter(object):
    def __init__(self, sock):
        self._socket = sock
        self._connection = sock.makefile('w+b', 1)
        self._queue = queue.Queue()
    
    def start(self):
        self._thread = gevent.spawn(self._run)
    
    def _run(self):
        while True:
            line = self._queue.get()
            
            if line == False:
                break
            
            try:
                self._connection.write(line + '\r\n')
            except:
                pass
    
        self._connection.close()
        self._socket.shutdown(socket.SHUT_RDWR)
        self._socket.close()
    
    def write_line(self, line):
        self._queue.put(line)
    
    def clear(self):
        while self._queue.get(block=False) != None:
            pass
    
    def close(self):
        self._queue.put(False)

def match_command(value):
    return match_param('command', value)

class _BaseConnection(object):
    MAX_LINELEN = 512

    connection_closed_event = Event()
    registration_event = Event()
    command_received_event = Event()

    def __init__(self, address, socket=None, factory=None):
        """
        Base class for IRC connections.

        address: A tuple containing the remote host/IP and port
                 of the connection
        socket: An existing socket for the connection, or None
                if a new connection is to be established.
        factory: The factory that was used to create this object.
        """

        self.socket_address = address
        self.socket = socket
        self.factory = factory

        evt = Event()
        evt.bind(self.__class__.connection_closed_event, filter=match_source(self))
        self.connection_closed_event = evt
        
        evt = Event()
        evt.bind(self.__class__.registration_event, filter=match_source(self))
        self.registration_event = evt
        
        evt = Event()
        evt.bind(self.__class__.command_received_event, filter=match_source(self))
        self.command_received_event = evt

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
        
        self._line_writer = QueuedLineWriter(self.socket)
        self._line_writer.start()

        try:
            self.handle_connection_made()

            connection = self.socket.makefile('w+b', 1)

            while True:
                line = connection.readline()

                if not line:
                    break

                self.process_line(line)
        except Exception:
            exc_info = sys.exc_info()
            sys.excepthook(*exc_info)
        finally:
            try:
                # Not calling possibly derived methods
                # as they might not be safe to call from here.
                _BaseConnection.close(self)
            except:
                pass

            self.__class__.connection_closed_event.invoke(self)

    def close(self, message=None):        
        if self._registration_timeout != None:
            self._registration_timeout.cancel()

        self._line_writer.close()

    def handle_exception(self, exc):
        pass

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

        if self.__class__.command_received_event.invoke(self, command=command, nickobj=nickobj, params=params):
            return

        self.handle_unknown_command(nickobj, command, params)

    def send_line(self, line):
        self._line_writer.write_line(line)

    def send_message(self, command, *parameter_list, **prefix):
        self.send_line(utils.format_irc_message(command, *parameter_list, **prefix))

    def handle_connection_made(self):
        self._registration_timeout = Timer(30, self._registration_timeout_timer)
        self._registration_timeout.start()

    def handle_unknown_command(self, command, nickobj, params):
        pass

    def register_user(self):
        self._registration_timeout.cancel()
        self._registration_timeout = None

        self.registered = True

        self.__class__.registration_event.invoke(self)

    def _registration_timeout_timer(self):
        self.handle_registration_timeout()
        
    def handle_registration_timeout(self):
        self.close('Registration timeout detected.')

class ConnectionFactory(object):
    new_connection_event = Event()

    def match_factory(value):
        def match_factory_helper(*args, **kwargs):
            return args[1].factory == value
        
        return lambda *args, **kwargs: match_factory_helper(*args, **kwargs)

    match_factory = staticmethod(match_factory)

    def __init__(self, cls):
        evt = Event()
        evt.bind(ConnectionFactory.new_connection_event, filter=match_source(self))
        self.new_connection_event = evt

        self._cls = cls

    def create(self, **kwargs):
        ircobj = self._cls(factory=self, **kwargs)

        self.__class__.new_connection_event.invoke(sender=self, connobj=ircobj)

        return ircobj

class IRCConnection(_BaseConnection):
    connection_closed_event = Event()
    registration_event = Event()
    command_received_event = Event()

    def __init__(self, address, socket=None, factory=None):
        _BaseConnection.__init__(self, address=address, socket=socket, factory=factory)
        
        self.reg_nickname = None
        self.reg_username = None
        self.reg_realname = None
        self.reg_password = None
        
    def handle_connection_made(self):
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
        if message != None:
            self.send_message('QUIT', message)

        _BaseConnection.close(self, message)

    def handle_unknown_command(self, nickobj, command, params):
        print "No idea how to handle this: command=", command, " - params=", params

    class CommandHandlers(object):
        _initialized = False
        
        def register_handlers():
            if IRCConnection.CommandHandlers._initialized:
                return
            
            IRCConnection.CommandHandlers._initialized = True
            
            IRCConnection.command_received_event.add_listener(IRCConnection.CommandHandlers.irc_PING,
                                                              Event.Handler, match_command('PING'))
            IRCConnection.command_received_event.add_listener(IRCConnection.CommandHandlers.irc_ERROR,
                                                              Event.Handler, match_command('ERROR'))
            IRCConnection.command_received_event.add_listener(IRCConnection.CommandHandlers.irc_001,
                                                              Event.PreObserver, match_command('001'))
            IRCConnection.command_received_event.add_listener(IRCConnection.CommandHandlers.irc_005,
                                                              Event.PreObserver, match_command('005'))
            IRCConnection.command_received_event.add_listener(IRCConnection.CommandHandlers.irc_375,
                                                              Event.PreObserver, match_command('375'))
            IRCConnection.command_received_event.add_listener(IRCConnection.CommandHandlers.irc_372,
                                                              Event.PreObserver, match_command('372'))
            IRCConnection.command_received_event.add_listener(IRCConnection.CommandHandlers.irc_NICK,
                                                              Event.PreObserver, match_command('NICK'))
            IRCConnection.command_received_event.add_listener(IRCConnection.CommandHandlers.irc_JOIN,
                                                              Event.PreObserver, match_command('JOIN'))
            IRCConnection.command_received_event.add_listener(IRCConnection.CommandHandlers.irc_PART,
                                                              Event.PreObserver, match_command('PART'))
            IRCConnection.command_received_event.add_listener(IRCConnection.CommandHandlers.irc_KICK,
                                                              Event.PreObserver, match_command('KICK'))
            IRCConnection.command_received_event.add_listener(IRCConnection.CommandHandlers.irc_QUIT,
                                                              Event.PreObserver, match_command('QUIT'))
            IRCConnection.command_received_event.add_listener(IRCConnection.CommandHandlers.irc_353,
                                                              Event.PreObserver, match_command('353'))
            IRCConnection.command_received_event.add_listener(IRCConnection.CommandHandlers.irc_366,
                                                              Event.PreObserver, match_command('366'))
            IRCConnection.command_received_event.add_listener(IRCConnection.CommandHandlers.irc_433,
                                                              Event.PreObserver, match_command('433'))
            IRCConnection.command_received_event.add_listener(IRCConnection.CommandHandlers.irc_331,
                                                              Event.PreObserver, match_command('331'))
            IRCConnection.command_received_event.add_listener(IRCConnection.CommandHandlers.irc_332,
                                                              Event.PreObserver, match_command('332'))
            IRCConnection.command_received_event.add_listener(IRCConnection.CommandHandlers.irc_333,
                                                              Event.PreObserver, match_command('333'))
            IRCConnection.command_received_event.add_listener(IRCConnection.CommandHandlers.irc_TOPIC,
                                                              Event.PreObserver, match_command('TOPIC'))
            IRCConnection.command_received_event.add_listener(IRCConnection.CommandHandlers.irc_329,
                                                              Event.PreObserver, match_command('329'))

        register_handlers = staticmethod(register_handlers)

        # PING :wineasy1.se.quakenet.org
        def irc_PING(evt, ircobj, command, nickobj, params):
            if len(params) < 1:
                return Event.Continue

            ircobj.send_message('PONG', params[0])

            return Event.Handled

        irc_PING = staticmethod(irc_PING)

        # ERROR :Registration timeout.
        def irc_ERROR(evt, ircobj, command, nickobj, params):
            ircobj.close()

            return Event.Handled            
            
        irc_ERROR = staticmethod(irc_ERROR)

        # :wineasy1.se.quakenet.org 001 shroud_ :Welcome to the QuakeNet IRC Network, shroud_
        def irc_001(evt, ircobj, command, nickobj, params):
            ircobj.me.nick = ircobj.reg_nickname

            ircobj.server = nickobj

            ircobj.register_user()

        irc_001 = staticmethod(irc_001)

        # :wineasy1.se.quakenet.org 005 shroud_ WHOX WALLCHOPS WALLVOICES USERIP CPRIVMSG CNOTICE \
        # SILENCE=15 MODES=6 MAXCHANNELS=20 MAXBANS=45 NICKLEN=15 :are supported by this server
        def irc_005(evt, ircobj, command, nickobj, params):
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
        def irc_375(evt, ircobj, command, nickobj, params):
            ircobj.motd = []

        irc_375 = staticmethod(irc_375)

        # :wineasy1.se.quakenet.org 372 shroud_ :- ** [ wineasy.se.quakenet.org ] **************************************** 
        def irc_372(evt, ircobj, command, nickobj, params):
            if len(params) < 2:
                return

            motdline = params[1]
            
            if motdline[:2] == '- ':
                motdline = motdline[2:]
            
            ircobj.motd.append(params[1])

        irc_372 = staticmethod(irc_372)

        # :shroud_!~shroud@p579F98A1.dip.t-dialin.net NICK :shroud__
        def irc_NICK(evt, ircobj, command, nickobj, params):
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
        def irc_JOIN(evt, ircobj, command, nickobj, params):
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
        def irc_PART(evt, ircobj, command, nickobj, params):
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
        def irc_KICK(evt, ircobj, command, nickobj, params):
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
        def irc_QUIT(evt, ircobj, command, nickobj, params):
            channels = list(nickobj.channels)
            
            for channel in channels:
                channel.remove_nick(nickobj)
            
        irc_QUIT = staticmethod(irc_QUIT)
        
        # :server.shroudbnc.info 353 sbncng = #sbncng :sbncng @shroud
        def irc_353(evt, ircobj, command, nickobj, params):
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
        def irc_366(evt, ircobj, command, nickobj, params):
            if len(params) < 2:
                return
            
            channel = params[1]
            
            if not channel in ircobj.channels:
                return
            
            channelobj = ircobj.channels[channel]

            channelobj.has_names = True
            
        irc_366 = staticmethod(irc_366)

        # :underworld2.no.quakenet.org 433 * shroud :Nickname is already in use.
        def irc_433(evt, ircobj, command, nickobj, params):
            if len(params) < 2 or ircobj.registered:
                return
            
            newnick = params[1] + '_'
            
            ircobj.reg_nickname = newnick
                
            ircobj.send_message('NICK', newnick)

        irc_433 = staticmethod(irc_433)
        
        # :underworld2.no.quakenet.org 331 #channel :No topic is set
        def irc_331(evt, ircobj, command, nickobj, params):
            if len(params) < 3:
                return
            
            channel = params[1]
            
            if not channel in ircobj.channels:
                return
            
            channelobj = ircobj.channels[channel]

            channelobj.topic_text = None
            channelobj.topic_nick = None
            channelobj.topic_time = None
            channelobj.has_topic = True
        
        irc_331 = staticmethod(irc_331)

        # :underworld2.no.quakenet.org 332 #channel :Some topic.
        def irc_332(evt, ircobj, command, nickobj, params):
            if len(params) < 3:
                return
            
            channel = params[1]
            
            if not channel in ircobj.channels:
                return
            
            channelobj = ircobj.channels[channel]

            channelobj.topic_text = params[2]
            
            if channelobj.topic_nick != None:
                channelobj.has_topic = True
                
        irc_332 = staticmethod(irc_332)

        # :underworld2.no.quakenet.org 333 #channel Nick 1297723476
        def irc_333(evt, ircobj, command, nickobj, params):
            if len(params) < 4:
                return
            
            channel = params[1]
            topic_nick = params[2]
            ts = params[3]
            
            if not channel in ircobj.channels:
                return
            
            channelobj = ircobj.channels[channel]

            channelobj.topic_nick = Nick(ircobj, topic_nick)
            channelobj.topic_time = datetime.fromtimestamp(int(ts))
            
            if channelobj.topic_text != None:
                channelobj.has_topic = True
                
        irc_333 = staticmethod(irc_333)
        
        # :shroud!shroud@help TOPIC #channel :new topic
        def irc_TOPIC(evt, ircobj, command, nickobj, params):
            if len(params) < 2:
                return
            
            channel = params[0]
            topic = params[1]
            
            if not channel in ircobj.channels:
                return
            
            channelobj = ircobj.channels[channel]
            
            channelobj.topic_text = topic
            channelobj.topic_nick = copy(nickobj)
            channelobj.topic_time = datetime.now()
            channelobj.has_topic = True
        
        irc_TOPIC = staticmethod(irc_TOPIC)
        
        # :underworld2.no.quakenet.org 329 shroud #sbfl 1233690341
        def irc_329(evt, ircobj, command, nickobj, params):
            if len(params) < 3:
                return
            
            channel = params[1]
            ts = params[2]
            
            if not channel in ircobj.channels:
                return
            
            channelobj = ircobj.channels[channel]
            
            channelobj.creation_time = datetime.fromtimestamp(int(ts))
            
        irc_329 = staticmethod(irc_329)

# Register built-in handlers for the IRCConnection class        
IRCConnection.CommandHandlers.register_handlers()

class ClientConnection(_BaseConnection):
    DEFAULT_SERVERNAME = 'server.shroudbnc.info'

    # See http://www.alien.net.au/irc/irc2numerics.html for details.
    rpls = {
        'RPL_WELCOME': (1, 'Welcome to the Internet Relay Network %s'),
        'RPL_ISUPPORT': (5, 'are supported by this server'),
        'RPL_NOTOPIC': (331, 'No topic is set'),
        'RPL_TOPIC': (332, None),
        'RPL_TOPICWHOTIME': (333, None),
        'RPL_NAMREPLY': (353, None),
        'RPL_ENDOFNAMES': (366, 'End of NAMES list'),
        'RPL_MOTDSTART': (375, '- %s Message of the day -'),
        'RPL_MOTD': (372, '- %s'),
        'RPL_ENDMOTD': (376, 'End of MOTD command'),
        'ERR_NOTEXTTOSEND': (412, 'No text to send'),
        'ERR_UNKNOWNCOMMAND': (421, 'Unknown command'),
        'ERR_NOMOTD': (422, 'MOTD File is missing'),
        'ERR_NONICKNAMEGIVEN': (431, 'No nickname given'),
        'ERR_ERRONEUSNICKNAME': (432, 'Erroneous nickname'),
        'ERR_NEEDMOREPARAMS': (461, 'Not enough parameters.'),
        'ERR_ALREADYREGISTRED': (462, 'Unauthorized command (already registered)')
    }

    connection_closed_event = Event()
    registration_event = Event()
    command_received_event = Event()
    authentication_event = Event()

    def __init__(self, address, socket, factory=None):
        _BaseConnection.__init__(self, address=address, socket=socket, factory=factory)

        self.me.host = self.socket_address[0]
        self.server.nick = ClientConnection.DEFAULT_SERVERNAME
        
        evt = Event()
        evt.bind(ClientConnection.authentication_event, filter=match_source(self))
        self.authentication_event = evt
        
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
            
        if text == None:
            text_list = []
        else:
            text_list = [text]

        return self.send_message(command, *[nick] + list(params) + text_list, \
                                **{'prefix': self.server})

    def handle_connection_made(self):
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

        self.__class__.authentication_event.invoke(self, username=self.me.user, password=self._password)
        
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
        _initialized = False
        
        def register_handlers():
            if ClientConnection.CommandHandlers._initialized:
                return
            
            ClientConnection.CommandHandlers._initialized = True

            ClientConnection.command_received_event.add_listener(ClientConnection.CommandHandlers.irc_USER,
                                                                 Event.Handler, match_command('USER'))
            ClientConnection.command_received_event.add_listener(ClientConnection.CommandHandlers.irc_NICK,
                                                                 Event.Handler, match_command('NICK'))
            ClientConnection.command_received_event.add_listener(ClientConnection.CommandHandlers.irc_PASS,
                                                                 Event.Handler, match_command('PASS'))
            ClientConnection.command_received_event.add_listener(ClientConnection.CommandHandlers.irc_QUIT,
                                                                 Event.Handler, match_command('QUIT'))
            ClientConnection.command_received_event.add_listener(ClientConnection.CommandHandlers.irc_VERSION,
                                                                 Event.Handler, match_command('VERSION'))
            ClientConnection.command_received_event.add_listener(ClientConnection.CommandHandlers.irc_MOTD,
                                                                 Event.Handler, match_command('MOTD'))
            ClientConnection.command_received_event.add_listener(ClientConnection.CommandHandlers.irc_NAMES,
                                                                 Event.Handler, match_command('NAMES'))
            ClientConnection.command_received_event.add_listener(ClientConnection.CommandHandlers.irc_TOPIC,
                                                                 Event.Handler, match_command('TOPIC'))

        register_handlers = staticmethod(register_handlers)

        # USER shroud * 0 :Gunnar Beutner
        def irc_USER(evt, ircobj, command, nickobj, params):
            if len(params) < 4:
                ircobj.send_reply('ERR_NEEDMOREPARAMS', 'USER')
                return Event.Handled

            if ircobj.registered:
                ircobj.send_reply('ERR_ALREADYREGISTRED')
                return Event.Handled

            ircobj.me.user = params[0]
            ircobj.realname = params[3]

            ircobj.register_user()
            
            return Event.Handled

        irc_USER = staticmethod(irc_USER)

        # NICK shroud_
        def irc_NICK(evt, ircobj, command, nickobj, params):
            if len(params) < 1:
                ircobj.send_reply('ERR_NONICKNAMEGIVEN', 'NICK')
                return Event.Handled

            nick = params[0]

            if nick == ircobj.me.nick:
                return Event.Handled

            if ' ' in nick:
                ircobj.send_reply('ERR_ERRONEUSNICKNAME', nick)
                return Event.Handled

            if not ircobj.registered:
                ircobj.me.nick = nick
                ircobj.register_user()
            else:
                ircobj.send_message('NICK', nick, prefix=ircobj.me)
                ircobj.me.nick = nick

            return Event.Handled

        irc_NICK = staticmethod(irc_NICK)

        # PASS topsecret
        def irc_PASS(evt, ircobj, command, nickobj, params):
            if len(params) < 1:
                ircobj.send_reply('ERR_NEEDMOREPARAMS', 'PASS')
                return Event.Handled

            if ircobj.registered:
                ircobj.send_reply('ERR_ALREADYREGISTRED')
                return Event.Handled

            ircobj._password = params[0]

            ircobj.register_user()
            
            return Event.Handled

        irc_PASS = staticmethod(irc_PASS)

        def irc_QUIT(evt, ircobj, command, nickobj, params):
            ircobj.close('Goodbye.')
            
            return Event.Handled

        irc_QUIT = staticmethod(irc_QUIT)

        # VERSION
        def irc_VERSION(evt, ircobj, command, nickobj, params):
            if len(params) > 0 or not ircobj.registered:
                return Event.Continue
            
            # TODO: missing support for RPL_VERSION
            
            attribs = []
            length = 0

            for key, value in ircobj.isupport.items():
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

            return Event.Handled

        irc_VERSION = staticmethod(irc_VERSION)

        # MOTD
        def irc_MOTD(evt, ircobj, command, nickobj, params):
            if not ircobj.registered:
                return Event.Continue
            
            if len(ircobj.motd) > 0:
                ircobj.send_reply('RPL_MOTDSTART', format_args=(ircobj.server))

                for line in ircobj.motd:
                    ircobj.send_reply('RPL_MOTD', format_args=(line))

                ircobj.send_reply('RPL_ENDMOTD')
            else:
                ircobj.send_reply('ERR_NOMOTD')
                
            return Event.Handled

        irc_MOTD = staticmethod(irc_MOTD)
        
        # NAMES #channel
        def irc_NAMES(evt, ircobj, command, nickobj, params):
            if len(params) != 1 or ',' in params[0] or not ircobj.registered:
                return Event.Continue
            
            channel = params[0]
            
            if channel not in ircobj.channels:
                return Event.Continue
            
            channelobj = ircobj.channels[channel]
            
            if not channelobj.has_names:
                return Event.Continue
            
            if channelobj.has_modes and 's' in channelobj.modes:
                chantype = '@'
            elif channelobj.has_modes and 'p' in channelobj.modes:
                chantype = '*'
            else:
                chantype = '='
            
            nicklist = []
            length = 0
            
            for nickobj, membership in channelobj.nicks.items():
                length += len(nickobj.nick)
                
                prefixes = ''
                
                for mode in membership.modes:
                    prefix = utils.mode_to_prefix(ircobj.isupport['PREFIX'], mode)
                    
                    if prefix != None:
                        prefixes += prefix
                
                nicklist.append(prefixes + nickobj.nick)
                
                if length > 300:
                    ircobj.send_reply('RPL_NAMREPLY', chantype, channel, ' '.join(nicklist))
                    nicklist = []
                    length = 0
            
            if length > 0:
                ircobj.send_reply('RPL_NAMREPLY', chantype, channel, ' '.join(nicklist))

            ircobj.send_reply('RPL_ENDOFNAMES', channel, prefix=ircobj.server)
            
            return Event.Handled
            
        irc_NAMES = staticmethod(irc_NAMES)

        # TOPIC #channel
        def irc_TOPIC(evt, ircobj, command, nickobj, params):
            if len(params) != 1 or not ircobj.registered:
                return Event.Continue
            
            channel = params[0]
            
            if channel not in ircobj.channels:
                return Event.Continue
            
            channelobj = ircobj.channels[channel]
            
            if not channelobj.has_topic:
                return Event.Continue
            
            if channelobj.topic_text == None:
                ircobj.send_reply('RPL_NOTOPIC', channel)
            else:
                ircobj.send_reply('RPL_TOPIC', channel, channelobj.topic_text)
                ircobj.send_reply('RPL_TOPICWHOTIME', channel, str(channelobj.topic_nick), \
                                  str(time.mktime(channelobj.topic_time.timetuple())))
                
            return Event.Handled

        irc_TOPIC = staticmethod(irc_TOPIC)
        
# Register built-in handlers for the ClientConnection class        
ClientConnection.CommandHandlers.register_handlers()

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
        self.modes = []
        self.join_time = datetime.now()
        self.creation_time = None

        self.topic_text = None
        self.topic_time = None
        self.topic_nick = None
        
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

    def _get_channels(self):
        for _, channelobj in self._ircobj.channels.items():
            if self in channelobj.nicks:
                yield channelobj

        raise StopIteration
    
    channels = property(_get_channels)
