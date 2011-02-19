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