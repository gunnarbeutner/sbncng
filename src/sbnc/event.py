class Event(object):
    """Multicast delegate used to handle events."""
    
    # Returned by an event handler to signal that we should
    # continue to invoke the remaining event handlers.
    CONTINUE = 1
    
    # Returned by an event handler to signal that no
    # further event handlers should be called.
    HANDLED = 2

    def __init__(self):
        self.handlers = set()
    
    def add_handler(self, other):
        """Registers an event handler."""
        
        self.handlers.add(other)
        return self
    
    def remove_handler(self, other):
        """Removes a handler from this event."""
        
        self.handlers.remove(other)
        return self
    
    def invoke(self, source, **kwargs):
        """
        Invokes the event handlers. Returns True if all event handlers
        were invoked, or False if one of them returned Event.HANDLED.
        """

        for handler in self.handlers:
            if handler(source, **kwargs) == Event.HANDLED:
                return False
            
        return True
