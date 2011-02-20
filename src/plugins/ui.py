from sbnc.plugin import Plugin, ServiceRegistry
from sbnc.utils import parse_irc_message

class UIPlugin(Plugin):
    _identity = '-sBNC!bouncer@shroudbnc.info'

    def __init__(self, service_registry):
        self._proxy = service_registry.get('info.shroudbnc.services.proxy')
        
        for user in self._proxy.users:
            userobj = self._proxy.users[user]
            
            for clientobj in userobj.client_connections:
                self._register_handlers(clientobj)
                
        self._proxy.client_registration_event.add_handler(self._client_registration_handler)
        
    def _client_registration_handler(self, evt, clientobj):
        self._register_handlers(clientobj)
        
    def _register_handlers(self, clientobj):
        clientobj.add_command_handler('PRIVMSG', self._client_privmsg_handler)
        clientobj.add_command_handler('SBNC', self._client_sbnc_handler)
        
    def _client_privmsg_handler(self, evt, clientobj, nickobj, params):
        if len(params) < 1:
            return

        target = params[0]
        targetobj = clientobj.get_nick(target)

        if targetobj.nick.upper() != '-SBNC':
            return

        evt.stop_handlers()

        if len(params) < 2:
            clientobj.send_message('ERR_NOTEXTTOSEND', prefix=clientobj.server)
            return

        text = params[1]
        
        tokens = parse_irc_message(text, can_have_prefix=False)
                
        if not self._handle_command(clientobj, tokens[1], tokens[2], False):
            clientobj.send_message('PRIVMSG', clientobj.me.nick, 'Unknown command. Try /msg -sBNC help',
                                   prefix=UIPlugin._identity)
    
    def _client_sbnc_handler(self, evt, clientobj, nickobj, params):
        evt.stop_handlers()
        
        if len(params) < 1:
            clientobj.send_reply('ERR_NEEDMOREPARAMS', prefix=clientobj.server)
            return
        
        if not self._handle_command(clientobj, params[0], params[1:], True):
            clientobj.send_message('NOTICE', clientobj.me.nick, 'Unknown command. Try /sbnc help',
                                   prefix=UIPlugin._identity)
    
    def _handle_command(self, clientobj, command, params, notice):
        pass

sr = ServiceRegistry.get_instance()
sr.register('info.shroudbnc.plugins.ui', UIPlugin(sr))