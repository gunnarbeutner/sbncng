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
