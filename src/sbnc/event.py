'''
Created on 07.02.2011

@author: Gunnar
'''

class Event(object):
    Continue = 1
    Handled = 2

    def __init__(self):
        self.handlers = set()
        
    def __add__(self, other):
        self.handlers.add(other)
    
    def __sub__(self, other):
        self.handlers.remove(other)
        
    def __call__(self, sender, eventargs):
        for handler in self.handlers:
            result = handler(sender, eventargs)
            
            if result == Event.Handled:
                return False
            
        return True