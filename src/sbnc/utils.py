import re

'''
Parses an IRC message, returns a tuple containing
the prefix (if any, None otherwise), the command and a list containing the arguments
'''
def parse_irc_message(line):
    tokens = line.split(' ')

    prefix = None
    args = []
    
    first = True
    last = False
    last_arg = None
    
    for token in tokens:
        if first and len(token) > 0 and token[0] == ':':
            token = token[1:]
            prefix = Hostmask(token)
            first = False

            continue
            
        first = False

        if len(token) > 0 and token[0] == ':':
            token = token[1:]
            last = True

        first = False

        if not last:
            args.append(token)
            continue
        
        if last_arg == None:
            last_arg = token
        else:
            last_arg = "%s %s" % (last_arg, token)
    
    if last_arg:
        args.append(last_arg)
    
    command = None

    if len(args) > 0:
        command = args[0]
        args = args[1:]

    return prefix, command, args

class Hostmask(object):
    _hostmask_regex = re.compile('^(.*)!(.*)@(.*)$')

    def __init__(self, mask=None):
        if isinstance(mask, Hostmask):
            self.nick = mask.nick
            self.user = mask.user
            self.host = mask.host
            return

        if mask != None:
            match = Hostmask._hostmask_regex.match(mask)
        else:
            match = False
                    
        if not match:
            self.nick = mask
            self.user = None
            self.host = None
        else:
            self.nick = match.group(1)
            self.user = match.group(2)
            self.host = match.group(3)

    def __str__(self):
        if self.user == None or self.host == None:
            return self.nick
        else:
            return '%s!%s@%s' % (self.nick, self.user, self.host)

    def __eq__(self, other):
        if other == None:
            return False

        return (self.nick == other.nick) and \
               (self.user == other.user) and \
               (self.host == other.host)
               
    def __ne__(self, other):
        return not self.__eq__(other)