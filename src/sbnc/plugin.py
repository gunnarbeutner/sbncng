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

class Service(object):
    """A service is a singleton object with a well-known name."""

    package = None
    """Package name for the service."""
    
class Plugin(Service):
    """A plugin is a service object that supports being controlled by users."""

    name = None
    """The name of the plugin."""

    description = None
    """A short description what this plugin does."""
    
    def unload(self):
        """
        Called when the plugin is to be unloaded, giving the plugin a chance to clean up.
        Plugins should return False in case they don't support unloading or can't
        be unloaded right now.
        """

        return False
    
class ServiceRegistry(object):
    """
    Service registry. Plugins can register service objects here which can be
    retrieved by other plugins using their package name.
    
    A service name is an FQDN in reverse order, e.g. info.shroudbnc.services.proxy
    
    Service objects should inherit from the Service class.
    """
    
    services = {}

    def register(cls):
        """
        Registers a new service.
        """
        
        if not issubclass(cls, Service):
            raise ValueError('Class must derive from Service class.')
        
        if cls.package in ServiceRegistry.services:
            return
        
        serviceobj = cls()
        cls.instance = serviceobj
        ServiceRegistry.services[cls.package] = serviceobj
        
    register = staticmethod(register)
        
    def get(name):
        """
        Retrieves a service object.
        """

        try:
            return ServiceRegistry.services[name]
        except KeyError:
            return None
        
    get = staticmethod(get)
