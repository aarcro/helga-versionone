import re
from functools import wraps, partial

import smokesignal
from twisted.internet import reactor, task
from v1pysdk import V1Meta

from helga import log, settings
from helga.db import db
from helga.plugins import command, match, random_ack, ResponseNotReady
from helga.util.encodings import to_unicode


logger = log.getLogger(__name__)
VERSIONONE_PATTERNS = set(['B', 'D', 'TK', 'AT', 'FG'])

v1 = None
Workitem = None
Team = None


class NotFound(Exception):
    pass


def bad_args(client, channel, nick, failure):
    failure.trap(TypeError)
    client.msg(channel, u'Umm... {0}, you might want to check the docs for that'.format(nick))


def deferred_to_channel(fn):
    @wraps(fn)
    def wrapper(client, channel, nick, *args):
        task.deferLater(
            reactor, 0, fn, client, channel, nick, *args
        ).addCallback(
            partial(client.msg, channel)
        ).addErrback(
            partial(bad_args, client, channel, nick)
        )
        raise ResponseNotReady
    return wrapper


def reload_v1(client, channel, nick):
    """Rebuild the V1 metadata, needed after meta data changes in the app"""
    global v1, Workitem, Team

    try:
        v1 = V1Meta(
            instance_url=settings.VERSIONONE_URL,
            username=settings.VERSIONONE_AUTH[0],
            password=settings.VERSIONONE_AUTH[1],
        )
        Workitem = v1.Workitem
        Team = v1.Team
    except AttributeError:
        logger.error('VersionOne plugin misconfigured, check your settings')
    return random_ack()


@deferred_to_channel
def team_command(client, channel, nick, *args):
    try:
        subcmd = args[0]
        args = args[1:]
    except IndexError:
        subcmd = 'list'

    # Find the named channel or create new
    q = {'name': channel}
    channel_settings = db.v1_channel_settings.find_one(q) or q
    teams = channel_settings.get('teams', {})
    # NB: White space is lost in command parsing, hope for the best
    name = ' '.join(args)

    if subcmd == 'list':
        return '\n'.join([
            '{0} {1}'.format(t, u) for t, u in teams.iteritems()
        ]) if teams else 'No teams found for {0}'.format(channel)
    elif subcmd == 'add':
        try:
            team = Team.where(Name=name).first()
        except IndexError:
            return 'I\'m sorry {0}, team name "{1}" not found'.format(nick, name)
        # Manually building a url is lame, but the url property on TeamRooms doesn't work
        teams[name] = (team.intid, ', '.join([
            '{0}/TeamRoom.mvc/Show/{1}'.format(settings.VERSIONONE_URL, r.intid) for r in team.Rooms
        ]) or team.url)
    elif subcmd == 'remove':
        try:
            del teams[name]
        except KeyError:
            return 'I\'m sorry {0}, team name "{1}" not found for {2}'.format(nick, name, channel)
    else:
        return 'No {0}, you can\'t {1}!'.format(nick, subcmd)
    # If we didn't return by now, save teams back to DB, and ack the user
    channel_settings['teams'] = teams
    db.v1_channel_settings.save(channel_settings)
    return random_ack()


def _get_review(item):
    for field in settings.VERSIONONE_CR_FIELDS:
        try:
            return getattr(item, field), field
        except AttributeError:
            pass
    # No candidate fields matched, number might not have been a valid type
    raise NotFound


@deferred_to_channel
def review_command(client, channel, nick, number, *args):
    """(review | cr) <issue> [!]<text>
        With no text, show review link
        With '!' before text replace link, otherwise append
    """

    try:
        w = Workitem.where(Number=number).first()
    except IndexError:
        return 'I\'m sorry {0}, item "{1}" not found'.format(nick, number)

    try:
        link, field = _get_review(w)
    except NotFound:
        # No candidate fields matched, number might not have been valid
        return 'I\'m sorry {0}, item "{1}" doesn\'t support reviews'.format(nick, number)

    if args is ():
        return '{0} Reviews: {1}'.format(number, link)

    # else append CR
    change = False
    new_link = ' '.join(args)
    if new_link[0] == '!':
        new_link = new_link[1:]
        change = True
    elif new_link not in link:
        new_link = ' '.join([link, new_link])
        change = True

    if change:
        logger.debug('On {0} change {1} to "{2}"'.format(number, field, new_link))
        if not getattr(settings, 'VERSIONONE_READONLY', True):
            setattr(w, field, new_link)
            v1.commit()
            logger.debug('commited')

        return random_ack()
    return 'Already got that one {0}'.format(nick)


@smokesignal.on('signon')
def init_versionone(*args, **kwargs):
    # Three require positionals because it's a subcommand
    reload_v1(None, None, None)


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
            '!v1 team[s] [add | remove | list] <teamname> -- add, remove, list team(s) for the channel',
            '!v1 take <ticket-id> - Add yourself to the ticket\'s Owners',
            '!v1 add [task | test] to <ticket-id> ... - Create a new task or test',
        ]
    logger.debug('Calling VersionOne subcommand {0} with args {1}'.format(subcmd, args))

    try:
        return COMMAND_MAP[subcmd](client, channel, nick, *args)
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
         'Usage: helga versionone reload | (take | [add (task | test) to]) <ticket-id>')
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
    'team': team_command,
    'teams': team_command,
    'review': review_command,
    'cr': review_command,
}
