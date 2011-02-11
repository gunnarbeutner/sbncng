from collections import defaultdict

class Event(object):
    """Multicast delegate used to handle events."""

    HIGH_PRIORITY = 1
    NORMAL_PRIORITY = 2
    LOW_PRIORITY = 3
    
    def __init__(self):
        self.handlers = defaultdict(set)
    
    def add_handler(self, handler, priority=NORMAL_PRIORITY):
        """Registers an event handler."""
        
        self.handlers[priority].add(handler)
    
    def remove_handler(self, handler):
        """Removes a handler from this event."""
        
        for k in self.handlers:
            if handler in self.handlers[k]:
                self.handlers[k].remove(handler)
    
    def invoke(self, source, **kwargs):
        """
        Invokes the event handlers. Returns True if all event handlers
        were invoked, or False if one of them returned Event.HANDLED.
        """

        assert source != None

        self.source = source

        try:
            for k in sorted(self.handlers.keys()):
                for handler in self.handlers[k]:
                    self._handlers_stopped = False
                    
                    handler(self, **kwargs)
                    
                    if self._handlers_stopped:
                        return False
        finally:
            del self.source

        return True
        
    def stop_handlers(self):
        self._handlers_stopped = True