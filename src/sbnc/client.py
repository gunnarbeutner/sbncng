import gevent, string
from gevent import socket
from sbnc import event, utils

class ClientConnection(object):
    servername = 'server.shroudbnc.info'

    rpls = {
        'RPL_WELCOME': (1, 'Welcome to the Internet Relay Network %s!%s@%s'),
        'ERR_UNKNOWNCOMMAND': (421, 'Unknown command'),
        'ERR_NONICKNAMEGIVEN': (431, 'No nickname given'),
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
        
        self.commands = {}

    def start(self):
        return gevent.spawn(self.run)
    
    def run(self):
        self.connection = self.socket.makefile()

        self.connectionMade()

        while True:
            line = self.connection.readline()
            
            if not line:
                break
            
            prefix, command, params = utils.parse_irc_message(line.rstrip('\r\n'))
            
            print prefix, command, params
            
            self.handleCommand(command, prefix, params)
        
        self.connection.close()
        
    def getHostmask(self):
        return "%s!%s@%s" % (self.nickname, self.username, self.hostname)

    def sendMessage(self, command, *parameter_list, **prefix):
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

    def sendReply(self, rpl, *params, **format_args):
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
        
        return self.sendMessage(command, *[nickname] + list(params) + [text], \
                                **{'prefix': ClientConnection.servername})

    def sendError(self, message):
        self.sendMessage('ERROR', message)

        self.socket.shutdown(socket.SHUT_RDWR)
        self.socket.close()

    def connectionMade(self):
        self.sendMessage('NOTICE', 'AUTH', '*** sbncng 0.1 - (c) 2011 Gunnar Beutner')
        self.sendMessage('NOTICE', 'AUTH', '*** Welcome to the brave new world.') 

    def handleCommand(self, command, prefix, params):
        if command in self.commands:
            result = self.commands[command]()
            
            if result == event.Event.Handled:
                return
        
        try:
            handler = getattr(self, 'irc_' + command)
        except AttributeError:
            handler = None
        
        if handler:
            handler(prefix, params)
        else:
            self.irc_unknown(prefix, command, params)

    def registerUser(self, nickname, username, password):
        assert not self.registered

        if self.nickname == None or self.username == None:
            return
        
        self.registered = True
        self.password = None
        
        self.sendReply('RPL_WELCOME', format_args=(self.nickname, self.username, self.hostname))

    def irc_USER(self, prefix, params):
        if len(params) < 4:
            self.sendReply('ERR_NEEDMOREPARAMS', 'USER')
            return

        if self.registered:
            self.sendReply('ERR_ALREADYREGISTRED')
            return

        self.username = params[0]
        self.realname = params[3]
        
        self.registerUser(self.nickname, self.username, self.password)
    
    def irc_unknown(self, prefix, command, params):
        self.sendReply('ERR_UNKNOWNCOMMAND', command, prefix=ClientConnection.servername)
    
    def irc_NICK(self, prefix, params):
        if len(params) < 1:
            self.sendReply('ERR_NONICKNAMEGIVEN', 'NICK')
            return

        if params[0] == self.nickname:
            return
        
        if not self.registered:
            self.nickname = params[0]
            self.registerUser(self.nickname, self.username, self.password)
            
            # TODO: send 001/motd, etc.
        else:
            self.sendMessage('NICK', params[0], prefix=self.getHostmask())
            self.nickname = params[0]

    def irc_PASS(self, prefix, params):
        if len(params) < 1:
            self.sendReply('ERR_NEEDMOREPARAMS', 'PASS')
            return
        
        if self.registered:
            self.sendReply('ERR_ALREADYREGISTRED')
            return
            
        self.password = params[0]

        self.registerUser(self.nickname, self.username, self.password)

    def irc_QUIT(self, prefix, params):
        self.sendError('Goodbye.')

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
