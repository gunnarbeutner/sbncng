#!/usr/bin/env python
from sbnc import irc, proxy
from sbnc.plugin import ServiceRegistry

proxy = proxy.Proxy()

sr = ServiceRegistry.get_instance()
sr.register('info.shroudbnc.services.proxy', proxy)

execfile('plugins/plugin101.py')

listener = irc.ClientListener( ('0.0.0.0', 9000), proxy.client_factory )
task = listener.start()

task.join()