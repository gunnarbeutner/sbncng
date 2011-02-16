from collections import defaultdict

class Event(object):
    """Multicast delegate used to handle events."""

    BUILTIN_PRIORITY = 0 # pseudo priority, used to specify the code that called this event
    LOW_PRIORITY = 1
    NORMAL_PRIORITY = 2
    HIGH_PRIORITY = 3
    
    def __init__(self):
        self._handlers = defaultdict(set)
    
    def add_handler(self, handler, priority=NORMAL_PRIORITY):
        """Registers an event handler."""
        
        if not priority in [Event.LOW_PRIORITY, Event.NORMAL_PRIORITY, Event.HIGH_PRIORITY]:
            raise ValueError("Invalid priority specified.")
        
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
                        (self._handlers_stopped_priority == None or k <= self._handlers_stopped_priority):
                    break

                handler(self, source, *args)

        return not self._handlers_stopped
    
    def get_handlers_count(self):
        """
        Returns the number of handlers that are currently registered
        for this event.
        """
        
        return len(self._handlers)
    
    handlers_count = property(get_handlers_count)
    
    def stop_handlers(self, priority=None):
        """
        Stops event handlers from being called for the current invocation. If
        a priority is specified only those handlers with a priority equal to
        or lower are stopped, otherwise all remaining handlers are skipped.
        """

        self._handlers_stopped_priority = priority
        self._handlers_stopped = True
