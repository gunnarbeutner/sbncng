import gevent

class Timer(object):
    def __init__(self, timeout, callback, *args):
        self._timeout = timeout
        self._callback = callback
        self._args = args
    
    def create(timeout, callback, *args):
        Timer(timeout, callback, *args).start()
        
    create = staticmethod(create)
    
    def start(self):
        gevent.spawn(self.run)
        
    def run(self):
        while True:
            gevent.sleep(self._timeout)
            
            if not self._callback(*self._args):
                break