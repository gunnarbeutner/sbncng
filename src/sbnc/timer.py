import gevent

class Timer(object):
    def __init__(self, interval, callback, *args):
        """
        Creates a new Timer object.
        """

        self._interval = interval
        self._callback = callback
        self._args = args
        self._greenlet = None
    
    def start(self):
        """
        Starts the timer and makes sure that the timer's callback
        function is invoked according to the interval specified
        in the call to the constructor. Returning false
        from the callback function will disable the timer.
        """

        if self._greenlet != None:
            return

        self._greenlet = gevent.spawn(self._run)

    def _run(self):
        """
        Runs the timer loop and calls the timer callback function
        continuously until it returns False.
        """

        while True:
            gevent.sleep(self._interval)

            if not self._callback(*self._args):
                break

    def cancel(self):
        """
        Disables the timer.
        """

        self._greenlet.kill(block=False)
        self._greenlet = None
