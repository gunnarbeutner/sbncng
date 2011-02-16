#!/usr/bin/env python
from sbnc import irc, proxy

p = proxy.Proxy()

listener = irc.ClientListener( ('0.0.0.0', 9000), p.client_factory )
task = listener.start()

task.join()