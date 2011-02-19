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

class Plugin(object):
    name = None
    """The name of the plugin."""

    description = None
    """A short description what this plugin does."""
    
    def unload(self):
        """
        Called when the plugin is to be unloaded, giving the plugin a chance to clean up.
        """

        pass
    
class ServiceRegistry(dict):
    """
    Service registry singleton class. Plugins can register service objects here which can be
    retrieved by other plugins using their name.
    
    A service name is an FQDN in reverse order, e.g. info.shroudbnc.services.proxy
    
    Service objects can be of any type.
    """
    
    _instance = None

    def __new__(cls, *args, **kwargs):
        # Make sure there's only ever one instance of the ServiceRegistry class
        if not cls._instance:
            cls._instance = super(ServiceRegistry, cls).__new__(
                                cls, *args, **kwargs)
        return cls._instance

    def get_instance():
        """
        Returns the ServiceRegistry singleton object.
        """

        return ServiceRegistry()
    
    get_instance = staticmethod(get_instance)

    def register(self, name, serviceobj):
        """
        Registers a new service.
        """
        
        self[name] = serviceobj
    
    def get(self, name):
        """
        Retrieves a service object.
        """

        try:
            return self[name]
        except IndexError:
            return None