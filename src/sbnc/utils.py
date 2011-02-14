import re
import string

def parse_irc_message(line):
    """Parses an IRC message, returns a tuple containing the prefix (if
    any, None otherwise), the command and a list containing the arguments"""

    tokens = line.split(' ')

    prefix = None
    args = []
    
    first = True
    last = False
    last_arg = None
    
    for token in tokens:
        if first and len(token) > 0 and token[0] == ':':
            token = token[1:]
            prefix = token
            first = False

            continue
            
        first = False

        if not last and len(token) > 0 and token[0] == ':':
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

def format_irc_message(command, *parameter_list, **prefix):
    params = list(parameter_list)

    message = ''

    if 'prefix' in prefix and prefix['prefix'] != None:
        message = ':' + str(prefix['prefix']) + ' '

    message = message + command

    if len(params) > 0:
        if len(params[-1]) > 0:
            params[-1] = ':' + params[-1]

        message = message + ' ' + string.join(params)

    return message

def parse_hostmask(hostmask):
    if isinstance(hostmask, dict):
        return hostmask

    nick = None
    user = None
    host = None
    
    if hostmask != None:
        match = _hostmask_regex.match(hostmask)
        
        if not match:
            nick = hostmask
        else:
            nick = match.group(1)
            user = match.group(2)
            host = match.group(3)

    return {
        'nick': nick,
        'user': user,
        'host': host
    }

_nickmodes_regex = re.compile('^\((.*?)\)(.*?)$')

def prefix_to_mode(prefixes, prefix):
    if prefix == '':
        return None
   
    match = _nickmodes_regex.match(prefixes)
    
    if not match:
        return None
    
    index = match.group(2).find(prefix)
    
    if index == -1:
        return None
    
    return match.group(1)[index]

def mode_to_prefix(prefixes, mode):
    if mode == '':
        return None
    
    match = _nickmodes_regex.match(prefixes)
    
    if not match:
        return None
    
    index = match.group(1).find(mode)
    
    if index == -1:
        return None
    
    return match.group(2)[index]
