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
            prefix = parse_hostmask(token)
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

_hostmask_regex = re.compile('^(.*)!(.*)@(.*)$')

def parse_hostmask(hostmask):
    if isinstance(hostmask, tuple):
        return hostmask

    match = _hostmask_regex.match(hostmask)
    
    if not match:
        return (hostmask, None, None)
    
    return (match.group(1), match.group(2), match.group(3))

def format_hostmask(hostmask_tuple):
    if isinstance(hostmask_tuple, str):
        return hostmask_tuple

    if hostmask_tuple[1] == None or hostmask_tuple[2] == None:
        return hostmask_tuple[0]
    else:
        return '%s!%s@%s' % hostmask_tuple
