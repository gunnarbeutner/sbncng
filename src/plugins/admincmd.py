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

import string
import random
from sbnc.proxy import Proxy
from sbnc.plugin import Plugin, ServiceRegistry
from plugins.ui import UIPlugin, UIAccessCheck

proxy_svc = ServiceRegistry.get(Proxy.package)
ui_svc = ServiceRegistry.get(UIPlugin.package)

class AdminCommandPlugin(Plugin):
    """Implements basic admin commands."""

    package = 'info.shroudbnc.plugins.admincmd'
    name = "AdminCmd"
    description = __doc__

    def __init__(self):
        ui_svc.register_command('adduser', self._cmd_adduser_handler, 'Admin', 'creates a new user',
                                'Syntax: adduser <username> [password]\nCreates a new user.', UIAccessCheck.admin)
        ui_svc.register_command('admin', self._cmd_admin_handler, 'Admin', 'gives someone admin privileges',
                                'Syntax: admin <username>\nGives admin privileges to a user.', UIAccessCheck.admin)
        ui_svc.register_command('broadcast', self._cmd_broadcast_handler, 'Admin', 'sends a global notice to all bouncer users',
                                'Syntax: broadcast <text>\nSends a notice to all currently connected users.', UIAccessCheck.admin)
        ui_svc.register_command('deluser', self._cmd_deluser_handler, 'Admin', 'removes a user',
                                'Syntax: deluser <username>\nDeletes a user.', UIAccessCheck.admin)
        ui_svc.register_command('die', self._cmd_die_handler, 'Admin', 'terminates the bouncer',
                                'Syntax: die\nTerminates the bouncer.', UIAccessCheck.admin)
        ui_svc.register_command('resetpass', self._cmd_resetpass_handler, 'Admin', 'sets a user\'s password',
                                'Syntax: resetpass <user> <password>\nResets another user\'s password.', UIAccessCheck.admin)
        ui_svc.register_command('simul', self._cmd_simul_handler, 'Admin', 'simulates a command on another user\'s connection',
                                'Syntax: simul <username> <command>\nExecutes a command in another user\'s context.', UIAccessCheck.admin)
        ui_svc.register_command('suspend', self._cmd_suspend_handler, 'Admin', 'suspends a user',
                                'Syntax: suspend <username> [reason]\nSuspends an account. An optional reason can be specified.', UIAccessCheck.admin)
        ui_svc.register_command('unadmin', self._cmd_unadmin_handler, 'Admin', 'removes someone\'s admin privileges',
                                'Syntax: unadmin <username>\nRemoves someone\'s admin privileges.', UIAccessCheck.admin)
        ui_svc.register_command('unsuspend', self._cmd_unsuspend_handler, 'Admin', 'unsuspends a user',
                                'Syntax: unsuspend <username>\nRemoves a suspension from the specified account.', UIAccessCheck.admin)
        ui_svc.register_command('who', self._cmd_who_handler, 'Admin', 'shows users',
                                'Syntax: who\nShows a list of all users.', UIAccessCheck.admin)
    
    @staticmethod
    def _random_password(length = 12):
        letters = string.ascii_letters + string.digits
        return ''.join([random.choice(letters) for _ in range(length)])
    
    def _cmd_adduser_handler(self, clientobj, params, notice):
        if len(params) < 1:
            ui_svc.send_sbnc_reply(clientobj, 'Syntax: adduser <username> [password]', notice)
            return
        
        user = params[0]
    
        if len(params) >= 2:
            password = params[1]
        else:
            password = AdminCommandPlugin._random_password()
            
        if user in proxy_svc.users:
            ui_svc.send_sbnc_reply(clientobj, 'The specified username is already in use.', notice)
            return

        userobj = proxy_svc.create_user(user)
        userobj.password = password
        
        if len(params) >= 2:
            ui_svc.send_sbnc_reply(clientobj, 'Done.', notice)
        else:
            ui_svc.send_sbnc_reply(clientobj, 'Done.' +
                                   ' The new user\'s password is \'%s\'.' % (password), notice)
        
    def _cmd_admin_handler(self, clientobj, params, notice):
        if len(params) < 1:
            ui_svc.send_sbnc_reply(clientobj, 'Syntax: admin <username>', notice)
            return
        
        user = params[0]
        
        if not user in proxy_svc.users:
            ui_svc.send_sbnc_reply(clientobj, 'There\'s no such user.', notice)
            return
            
        userobj = proxy_svc.users[user]
        
        userobj.admin = True
        
        ui_svc.send_sbnc_reply(clientobj, 'Done.', notice)

    def broadcast(self, message):
        for userobj in proxy_svc.users.values():
            for subclientobj in userobj.client_connections:
                ui_svc.send_sbnc_reply(subclientobj, 'Global message: %s' % (message), notice=False)

    def _cmd_broadcast_handler(self, clientobj, params, notice):
        if len(params) < 1:
            ui_svc.send_sbnc_reply(clientobj, 'Syntax: broadcast <text>', notice)
            return
        
        self.broadcast(' '.join(params))       
        
        ui_svc.send_sbnc_reply(clientobj, 'Done.', notice)
        
        pass
        
    def _cmd_deluser_handler(self, clientobj, params, notice):
        if len(params) < 1:
            ui_svc.send_sbnc_reply(clientobj, 'Syntax: deluser <username>', notice)
            return

        user = params[0]
        
        if not user in proxy_svc.users:
            ui_svc.send_sbnc_reply(clientobj, 'There\'s no such user.', notice)
            return
        
        proxy_svc.remove_user(user)
        
        ui_svc.send_sbnc_reply(clientobj, 'Done.')
        
    def _cmd_die_handler(self, clientobj, params, notice):
        # TODO: implement
        pass
        
    def _cmd_resetpass_handler(self, clientobj, params, notice):
        if len(params) < 1:
            ui_svc.send_sbnc_reply(clientobj, 'Syntax: resetpass <username> [password]', notice)
            return
        
        user = params[0]
        
        if not user in proxy_svc.users:
            ui_svc.send_sbnc_reply(clientobj, 'There\'s no such user.', notice)
            return
        
        if len(params) >= 2:
            password = params[1]
        else:
            password = AdminCommandPlugin._random_password()
            
        userobj = proxy_svc.users[user]
        userobj.password = password
        
        if len(params) >= 2:
            ui_svc.send_sbnc_reply(clientobj, 'Done.', notice)
        else:
            ui_svc.send_sbnc_reply(clientobj, 'Done.' +
                                   ' The user\'s password was changed to \'%s\'.' % (password), notice)
                
    def _cmd_simul_handler(self, clientobj, params, notice):
        if len(params) < 2:
            ui_svc.send_sbnc_reply(clientobj, 'Syntax: simul <username> <command>', notice)
            return
        
        # TODO: implement
        
        pass
        
    def _cmd_suspend_handler(self, clientobj, params, notice):
        if len(params) < 1:
            ui_svc.send_sbnc_reply(clientobj, 'Syntax: suspend <username> [reason]', notice)
            return
        
        # TODO: implement
        
        pass
        
    def _cmd_unadmin_handler(self, clientobj, params, notice):
        if len(params) < 1:
            ui_svc.send_sbnc_reply(clientobj, 'Syntax: unadmin <username>', notice)
            return
        
        user = params[0]
        
        if not user in proxy_svc.users:
            ui_svc.send_sbnc_reply(clientobj, 'There\'s no such user.', notice)
            return
            
        userobj = proxy_svc.users[user]
        
        userobj.admin = False
        
        ui_svc.send_sbnc_reply(clientobj, 'Done.', notice)
        
    def _cmd_unsuspend_handler(self, clientobj, params, notice):
        if len(params) < 1:
            ui_svc.send_sbnc_reply(clientobj, 'Syntax: unsuspend <username>', notice)
            return
        
        # TODO: implement
        
        pass
        
    def _cmd_who_handler(self, clientobj, params, notice):
        # TODO: implement
        
        pass

ServiceRegistry.register(AdminCommandPlugin)
