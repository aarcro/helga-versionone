import random
import re

import smokesignal

from twisted.internet import reactor

from v1pysdk import V1Meta

from helga import log, settings
from helga.db import db
from helga.plugins import command, match, ACKS, ResponseNotReady
from helga.util.encodings import to_unicode


logger = log.getLogger(__name__)
VERSIONONE_PATTERNS = set(['B', 'D', 'TK', 'AT', 'FG'])

v1 = None
Workitem = None


def reload_v1():
    """Rebuild the V1 metadata, needed after meta data changes in the app"""
    global v1, Workitem

    try:
        v1 = V1Meta(
            instance_url=settings.VERSIONONE_URL,
            username=settings.VERSIONONE_AUTH[0],
            password=settings.VERSIONONE_AUTH[1],
        )
        Workitem = v1.Workitem
    except AttributeError:
        logger.error('VersionOne plugin misconfigured, check your settings')
    return random.choice(ACKS)


@smokesignal.on('signon')
def init_versionone(*args, **kwargs):
    reload_v1()


def find_versionone_numbers(message):
    """
    Finds all versionone ticket numbers in a message. This will ignore any that already
    appear in a URL
    """

    pat = r'\b(({0})-\d+)\b'.format('|'.join(VERSIONONE_PATTERNS))
    tickets = []
    for ticket in re.findall(pat, message, re.IGNORECASE):
        tickets.append(ticket[0])

    return tickets


def versionone_command(client, channel, nick, message, cmd, args):
    """
    Command handler for the versionone plugin
    """
    try:
        subcmd = args.pop(0)
    except IndexError:
        return [
            'Usage for versionone (alias v1)',
            '!v1 reload - Reloads metadata from V1 server',
        ]
    logger.debug('Calling VersionOne subcommand {0} with args {1}'.format(subcmd, args))

    try:
        return COMMAND_MAP[subcmd](*args)
    except KeyError:
        return u'Umm... {0}, Never heard of it?'.format(subcmd)
    except TypeError:
        return u'Umm... {0}, you might want to check the docs for {1}'.format(nick, subcmd)

    return None


def versionone_full_descriptions(client, channel, numbers):
    """
    Meant to be run asynchronously because it uses the network
    """

    descriptions = [
        '[{number}] {name} ({url})'.format(**{
            'name': s.Name,
            'number': s.Number,
            'url': s.url,
        })
        for s in Workitem.filter(
            # OR join on each number
            '|'.join(["Number='{0}'".format(n) for n in numbers])
        ).select('Name', 'Number')
    ]

    if descriptions:
        client.msg(channel, '\n'.join(descriptions))


def versionone_match(client, channel, nick, message, matches):
    # do the fetching with a deferred
    reactor.callLater(0, versionone_full_descriptions, client, channel, matches)
    raise ResponseNotReady


@match(find_versionone_numbers)
@command('versionone', aliases=['v1'], help='Interact with VersionOne tickets.'
         'Usage: helga versionone reload')
def versionone(client, channel, nick, message, *args):
    """
    A plugin for showing URLs to VERSIONONE ticket numbers. This is both a set of commands to
    interact with tickets, and a match to automatically show them.

    Issue numbers are automatically detected.
    """
    if len(args) == 2:
        # args = [cmd, args]
        fn = versionone_command
    else:
        # args = [matches]
        fn = versionone_match
    return fn(client, channel, nick, message, *args)

COMMAND_MAP = {
    'reload': reload_v1,
}

