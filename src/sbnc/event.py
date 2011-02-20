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

        if not self._handlers_stopped or priority > self._handlers_stopped_priority: 
            self._handlers_stopped_priority = priority

        self._handlers_stopped = True
