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

class UIAccessCheck(object):
    """Helper functions for checking users' access."""

    def anyone(clientobj):
        """Returns True for any user."""

        return True
    
    anyone = staticmethod(anyone)
    
    def admin(clientobj):
        """Returns True for any user who is an admin."""
 
        return ('admin' in clientobj.config and clientobj.config['admin'])

    admin = staticmethod(admin)

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
        
        # register handlers for existing client connections
        for user in proxy_svc.users:
            userobj = proxy_svc.users[user]
            
            for clientobj in userobj.client_connections:
                self._register_handlers(clientobj)
        
        # make sure new clients also get the event handlers
        proxy_svc.client_registration_event.add_handler(self._client_registration_handler)
        
        self.register_command('help', self._cmd_help_handler, 'User',
                              'displays a list of commands or information about individual commands',
                              'Syntax: help [command]\nDisplays a list of commands or information about individual commands.')
        
    def _client_registration_handler(self, evt, clientobj):
        self._register_handlers(clientobj)
        
    def _register_handlers(self, clientobj):
        """Registers handlers for /msg -sBNC <command> and /sbnc <command>"""
        
        clientobj.add_command_handler('PRIVMSG', self._client_privmsg_handler)
        clientobj.add_command_handler('SBNC', self._client_sbnc_handler)
        
    def _client_privmsg_handler(self, evt, clientobj, nickobj, params):
        """
        PRIVMSG handler. Checks whether the target is '-sBNC' and passes the command
        to _handle_command.
        """

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
            self.send_sbnc_reply(clientobj, 'Unknown command. Try /msg -sBNC help', notice=True)
    
    def _client_sbnc_handler(self, evt, clientobj, nickobj, params):
        """
        SBNC handler. Checks whether we have enough parameters and passes the command
        to _handle_command.
        """

        evt.stop_handlers()
        
        if len(params) < 1:
            clientobj.send_reply('ERR_NEEDMOREPARAMS', prefix=clientobj.server)
            return
        
        if not self._handle_command(clientobj, params[0], params[1:], True):
            self.send_sbnc_reply(clientobj, 'Unknown command. Try /msg -sBNC help', notice=False)
    
    def _handle_command(self, clientobj, command, params, notice):
        """Handles the command."""

        if command in self.commands:
            if not self.commands[command]['access_check'](clientobj):
                return

            self.commands[command]['callback'](clientobj, params, notice)
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
            
            for command in self.commands:
                cmdobj = self.commands[command]
                
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
