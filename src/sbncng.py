from sbnc import irc

listener = irc.IRCServerListener( ('0.0.0.0', 9000) )
task = listener.start()

def new_conn_handler(event):
    event.source.registration_successful_event.add_handler(registration_event)

def registration_event(event):
    event.source.send_message('JOIN', '#sbncng')
    event.source.command_events['PRIVMSG'].add_handler(privmsg_handler)

def privmsg_handler(event, prefix, params):
    nick = prefix.split('!')[0]
    chan = params[0]
    msg = params[1]
    
    if msg == '!die':
        event.source.close('Bai!')

irc.IRCClientConnection.new_connection_event.add_handler(new_conn_handler)

s = irc.IRCClientConnection(addr=('irc.quakenet.org', 6667))
s.nickname = 'sbncng'
s.username = 'sbncng'
s.start()

task.join()