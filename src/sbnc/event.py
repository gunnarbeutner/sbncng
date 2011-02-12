from collections import defaultdict

class Event(object):
    """Multicast delegate used to handle events."""

    HIGH_PRIORITY = 1
    NORMAL_PRIORITY = 2
    LOW_PRIORITY = 3
    
    def __init__(self):
        self._handlers = defaultdict(set)
    
    def add_handler(self, handler, priority=NORMAL_PRIORITY):
        """Registers an event handler."""
        
        self._handlers[priority].add(handler)
    
    def remove_handler(self, handler):
        """Removes a handler from this event."""
        
        for k in self._handlers:
            if handler in self._handlers[k]:
                self._handlers[k].remove(handler)
    
    def invoke(self, source, *args):
        """
        Invokes the event _handlers. Returns True if all event _handlers
        were invoked, or False if one of them returned Event.HANDLED.
        """

        # TODO: figure out whether we want to catch exceptions here
        # and log them in a user-friendly fashion

        self._handlers_stopped = False

        for k in sorted(self._handlers.keys()):
            for handler in self._handlers[k]:
                if self._handlers_stopped and \
                        (self._handlers_stopped_priority == None or k >= self._handlers_stopped_priority):
                    break

                handler(self, source, *args)

        return not self._handlers_stopped
    
    def get_handlers_count(self):
        return len(self._handlers)
    
    handlers_count = property(get_handlers_count)
    
    def stop_handlers(self, priority=None):
        self._handlers_stopped_priority = priority
        self._handlers_stopped = True