#!/usr/bin/env python
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

try:
    import pydevd

    # Try to enable post-mortem debugging for exceptions
    pydevd.set_pm_excepthook()
except ImportError:
    pass

from sbnc.irc import ClientListener
from sbnc.proxy import Proxy
from sbnc.plugin import ServiceRegistry

proxy_svc = ServiceRegistry.get(Proxy.package)

execfile('plugins/plugin101.py')
execfile('plugins/ui.py')
execfile('plugins/awaycmd.py')
execfile('plugins/admincmd.py')
execfile('plugins/querylog.py')

listener = ClientListener( ('0.0.0.0', 9000), proxy_svc.client_factory )
task = listener.start()

task.join()