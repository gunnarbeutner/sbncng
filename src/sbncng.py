from sbnc import irc

listener = irc.IRCServerListener( ('0.0.0.0', 9000) )
task = listener.start()

def foo(target):
    target.registration_successful_event.add_handler(bar)
    target.command_events['USER'].add_handler(baz)

def bar(target):
    print target
    
def baz(target, prefix, params):
    print "FOO"
    print prefix, params

irc.IRCServerConnection.connection_made_event.add_handler(foo)

s = irc.IRCClientConnection(addr=('irc.quakenet.org', 6667))
s.nickname = 'sbncng'
s.username = 'sbncng'
s.start()

task.join()