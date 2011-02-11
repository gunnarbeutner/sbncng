from sbnc import irc

listener = irc.IRCServerListener( ('0.0.0.0', 9000) )
task = listener.start()

def new_conn_handler(event, ircobj):
    ircobj.registration_successful_event.add_handler(registration_event)

def registration_event(event, ircobj):
    ircobj.send_message('JOIN', '#sbncng')
    ircobj.command_events['PRIVMSG'].add_handler(privmsg_handler)

def privmsg_handler(event, ircobj, prefix, params):
    nick = prefix[0]
    chan = params[0]
    msg = params[1]
    
    if msg == '!die':
        ircobj.close('Bye!')

irc.IRCClientConnection.new_connection_event.add_handler(new_conn_handler)

s = irc.IRCClientConnection(addr=('irc.quakenet.org', 6667))
s.attempted_nickname = 'sbncng'
s.username = 'sbncng'
s.start()

task.join()