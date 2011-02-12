from sbnc import irc, proxy

p = proxy.Proxy()

listener = irc.ServerListener( ('0.0.0.0', 9000), p.client_factory )
task = listener.start()

#def new_conn_handler(event, factory, ircobj):
#    ircobj.registration_event.add_handler(registration_event)
#
#def registration_event(event, ircobj):
#    ircobj.send_message('JOIN', '#sbncng')
#    ircobj.add_command_handler('PRIVMSG', privmsg_handler)
#
#def privmsg_handler(event, ircobj, prefix, params):
#    nick = prefix[0]
#    chan = params[0]
#    msg = params[1]
#    
#    if msg == '!die':
#        ircobj.close('Bye!')
#        
#    print '\n'.join(ircobj.motd)
#
#client_factory = irc.ConnectionFactory(irc.ClientConnection)
#client_factory.new_connection_event.add_handler(new_conn_handler)
#
#s = client_factory.create(addr=('irc.quakenet.org', 6667))
#s.attempted_nickname = 'sbncng'
#s.username = 'sbncng'
#s.realname = 'sbncng client'
#s.start()

task.join()