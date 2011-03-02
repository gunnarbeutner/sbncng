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

from sbnc.plugin import Plugin, ServiceRegistry
from sbnc.proxy import Proxy
from sbnc.utils import parse_irc_message
from sbnc.event import Event
from sbnc.irc import match_command

class UIAccessCheck(object):
    """Helper functions for checking users' access."""

    @staticmethod
    def anyone(clientobj):
        """Returns True for any user."""

        return True

    @staticmethod    
    def admin(clientobj):
        """Returns True for any user who is an admin."""
 
        return ('admin' in clientobj.owner.config and clientobj.owner.config['admin'])

proxy_svc = ServiceRegistry.get(Proxy.package)

class UIPlugin(Plugin):
    """User interface plugin. Provides support for /msg -sBNC <command> and /sbnc <command>"""

    package = 'info.shroudbnc.plugins.ui'
    name = 'UIPlugin'
    description = __doc__

    _identity = '-sBNC!bouncer@shroudbnc.info'

    def __init__(self):
        self.commands = {}
        self.settings = {}
        self.usersettings = {}
        
        proxy_svc.client_command_received_event.add_listener(self._client_privmsg_handler,
                                                             Event.Handler,
                                                             filter=match_command('PRIVMSG'))

        proxy_svc.client_command_received_event.add_listener(self._client_sbnc_handler,
                                                             Event.Handler,
                                                             filter=match_command('SBNC'))
        
        self.register_command('help', self._cmd_help_handler, 'User',
                              'displays a list of commands or information about individual commands',
                              'Syntax: help [command]\nDisplays a list of commands or information about individual commands.')
        
    def _client_privmsg_handler(self, evt, clientobj, command, nickobj, params):
        """
        PRIVMSG handler. Checks whether the target is '-sBNC' and passes the command
        to _handle_command.
        """

        if not clientobj.registered or len(params) < 1:
            return Event.Continue

        target = params[0]
        targetobj = clientobj.get_nick(target)

        # TODO: use the nick from _identity
        if targetobj.nick.upper() != '-SBNC':
            return Event.Continue

        if len(params) < 2:
            clientobj.send_message('ERR_NOTEXTTOSEND', prefix=clientobj.server)
            return Event.Handled

        text = params[1]
        
        tokens = parse_irc_message(text, can_have_prefix=False)
                
        if not self._handle_command(clientobj, tokens[1], tokens[2], False):
            # TODO: use the nick from _identity
            self.send_sbnc_reply(clientobj, 'Unknown command. Try /msg -sBNC help', notice=False)
    
        return Event.Handled
    
    def _client_sbnc_handler(self, evt, clientobj, command, nickobj, params):
        """
        SBNC handler. Checks whether we have enough parameters and passes the command
        to _handle_command.
        """

        if len(params) < 1:
            clientobj.send_reply('ERR_NEEDMOREPARAMS', prefix=clientobj.server)
            return Event.Handled
        
        if not self._handle_command(clientobj, params[0], params[1:], True):
            # TODO: use the nick from _identity
            self.send_sbnc_reply(clientobj, 'Unknown command. Try /sbnc help', notice=True)
    
        return Event.Handled
    
    def _handle_command(self, clientobj, command, params, notice):
        """Handles the command."""

        if command in self.commands:
            cmdobj = self.commands[command]
            
            if not cmdobj['access_check'](clientobj):
                return False

            cmdobj['callback'](clientobj, params, notice)
            return True

    def register_command(self, name, callback, category, description,
                         help_text, access_check=UIAccessCheck.anyone):
        self.commands[name] = {
            'callback': callback,
            'category': category,
            'description': description,
            'help_text': help_text,
            'access_check': access_check
        }
    
    def unregister_command(self, name):
        del self.commands[name]
    
    def register_setting(self, name):
        pass
    
    def unregister_setting(self, name):
        pass
    
    def register_usersetting(self, name):
        pass
    
    def unregister_usersetting(self, name):
        pass

    def send_sbnc_reply(self, clientobj, message, notice=False):
        if notice:
            type = 'NOTICE'
        else:
            type = 'PRIVMSG'

        clientobj.send_message(type, clientobj.me.nick, message, prefix=UIPlugin._identity)

    def _cmd_help_handler(self, clientobj, params, notice):
        if len(params) > 0:
            command = params[0]
            
            if not command in self.commands or not self.commands[command]['access_check'](clientobj):
                self.send_sbnc_reply(clientobj, 'There is no such command.', notice)
                return
            
            for line in self.commands[command]['help_text'].split('\n'):
                self.send_sbnc_reply(clientobj, line, notice)
        else:
            self.send_sbnc_reply(clientobj, '--The following commands are available to you--', notice)
            self.send_sbnc_reply(clientobj, '--Used as \'/sbnc <command>\', or \'/msg -sbnc <command>\'', notice)
            
            cmds = {}
            
            for command, cmdobj in self.commands.items():
                if not cmdobj['access_check'](clientobj):
                    continue
                
                if not cmdobj['category'] in cmds:
                    cmds[cmdobj['category']] = {}
                    
                cmds[cmdobj['category']][command] = cmdobj
                
            for category in sorted(cmds):
                self.send_sbnc_reply(clientobj, '--', notice)
                self.send_sbnc_reply(clientobj, category + ' commands', notice)
                
                for command in sorted(cmds[category]):
                    cmdobj = cmds[category][command]
                    
                    self.send_sbnc_reply(clientobj, command +  ' - ' + cmdobj['description'], notice)
                    
            self.send_sbnc_reply(clientobj, 'End of HELP.', notice)

ServiceRegistry.register(UIPlugin)
