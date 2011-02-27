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

def match_source(value):
    def match_source_helper(*args, **kwargs):
        return args[1] == value
    
    return lambda *args, **kwargs: match_source_helper(*args, **kwargs)

def match_param(key, value):
    def match_param_helper(*args, **kwargs):
        return kwargs[key] == value
    
    return lambda *args, **kwargs: match_param_helper(*args, **kwargs)

def lambda_and(expr1, expr2):
    def lambda_and_helper(*args, **kwargs):
        return expr1(*args, **kwargs) and expr2(*args, **kwargs)
    
    return lambda *args, **kwargs:  lambda_and_helper(*args, **kwargs)

class Event(object):
    """Multicast delegate used to handle events."""

    PreObserver = 0
    Handler = 1
    PostObserver = 2
    
    Continue = 1
    Handled = 2
    RemoveHandler = 4

    def __init__(self):
        self.handlers = []

        self.filter = None
        self.parent = None
    
    def bind(self, other, filter=filter):
        """Binds this to another event using the optionally specified filter."""
        assert len(self.handlers) == 0
        
        self.filter = filter
        self.parent = other
        
    def unbind(self, event):
        """Unbinds this event from another event."""
        raise NotImplementedError()
    
    def add_listener(self, receiver, type, filter=None, last=False):
        """Registers an event handler."""
        
        if self.filter != None:
            if filter == None:
                filter = self.filter
            else:
                filter = lambda_and(self.filter, filter)

        handler = (receiver, type, filter)
        
        if last:
            self.handlers.append(handler)
        else:
            self.handlers.insert(0, handler)
        
        if self.parent != None:
            self.parent.add_listener(receiver, type, filter=filter, last=last)

# TODO: implement  
    def remove_listener(self, receiver, type, filter=any):
        """Removes a handler from this event."""
        raise NotImplementedError()
    
    def invoke(self, sender, **kwargs):
        """
        Invokes the event handlers. Returns True if a handler called stop_handlers().
        """

        handled = False

        for type in [Event.PreObserver, Event.Handler, Event.PostObserver]:
            for handler in self.handlers:
                if handler[1] != type:
                    continue

                if type != Event.Handler:
                    handled = False
                    
                self.handled = handled

                if handler[2] != None and \
                        not handler[2](self, sender, **kwargs):
                    continue

                result = handler[0](self, sender, **kwargs)
                
                if type == Event.Handler:
                    if not result in [Event.Continue, Event.Handled, Event.RemoveHandler]:
                        raise ValueError('Handler must return one of Event.Continue, ' +
                                         'Event.Handled and Event.RemoveHandler')
                        
                    if result & Event.RemoveHandler:
                        # TODO: remove the handler
                        raise NotImplementedError()
                    
                    if result & Event.Handled:
                        handled = True
                        break
                else:
                    if result != None:
                        raise ValueError('PreObserver and PostObserver callback functions ' +
                                         'must return None.')

        return handled
