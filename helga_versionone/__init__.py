import re
from functools import wraps, partial
from collections import defaultdict

from oauth2client.client import OAuth2Credentials, OAuth2WebServerFlow, FlowExchangeError
from twisted.internet import reactor, task
from twisted.internet.defer import Deferred
from urllib2 import HTTPError

from helga import log, settings
from helga.db import db
from helga.plugins import command, match, random_ack, ResponseNotReady


USE_OAUTH = getattr(settings, 'VERSIONONE_OAUTH_ENABLED', False)
if USE_OAUTH:
    from helga_versionone.v1_wrapper import HelgaV1Meta as V1Meta  # pragma: no cover
else:
    from v1pysdk import V1Meta

logger = log.getLogger(__name__)
VERSIONONE_PATTERNS = set(['B', 'D', 'TK', 'AT', 'FG', 'I', 'R', 'E'])
# Non-workitems, need different endpoints
SPECIAL_PATTERNS = {
    'I': 'Issue',
    'R': 'Request',
}


class NotFound(Exception):
    pass


class QuitNow(Exception):
    pass


def bad_auth(v1, client, channel, nick, failure):
    failure.trap(HTTPError)
    logger.debug('bag_auth failure="{0}"'.format(failure))
    client.msg(channel, u'{0}, You probably need to reset your token, try "!v1 token"'.format(nick))


def bad_args(v1, client, channel, nick, failure):
    failure.trap(TypeError, AttributeError, HTTPError)
    logger.debug('bag_args failure="{0}"'.format(failure))

    if v1 is None:
        client.msg(channel, u'{0}, you might want to try "!v1 oauth" or "!v1 token"'.format(nick))
    else:
        logger.warning('Check docs because', exc_info=True)
        client.msg(channel, u'Umm... {0}, you might want to check the docs for that'.format(nick))


def quit_now(client, channel, nick, failure):
    failure.trap(QuitNow)
    client.msg(channel, failure.value.message.format(channel=channel, nick=nick))


class deferred_response(object):
    def __init__(self, target):
        self.target = target

    def __call__(self, fn):
        @wraps(fn)
        def wrapper(v1, client, channel, nick, *args):
            d = task.deferLater(
                reactor, 0, fn, v1, client, channel, nick, *args
            ).addCallback(
                partial(client.msg, locals()[self.target])
            ).addErrback(
                partial(bad_auth, v1, client, channel, nick)
            ).addErrback(
                partial(bad_args, v1, client, channel, nick)
            ).addErrback(
                partial(quit_now, client, channel, nick)
            )
            logger.debug('Delaying exection of {0}'.format(fn.__name__))
            return d
        return wrapper

deferred_to_channel = deferred_response('channel')
deferred_to_nick = deferred_response('nick')


def commit_changes(v1, *args):
    """Respect the READONLY setting, return ack, or no perms message
       args is a list of 3-tuples, that will be passed to setattr iff we will write to V1

       Because of the V1Meta caching, strange things happen if you make changes and don't actually commit
       So only make the changes when commiting.
    """
    if getattr(settings, 'VERSIONONE_READONLY', True):
        return 'I would, but I\'m not allowed to write :('

    for call in args:
        setattr(*call)

    v1.commit()
    return random_ack()


def create_object(Klass, **kwargs):
    """Respect the READONLY setting return the object or raise QuitNow
       kwargs are passed to Klass.create()

    """
    if getattr(settings, 'VERSIONONE_READONLY', True):
        raise QuitNow('I\'m sorry {nick}, write access is disabled')

    return Klass.create(**kwargs)


def _get_things(Klass, workitem, *args):
    if not args:
        args = ['Name', 'Status.Name', 'Status.Order']
    return Klass.where(Parent=workitem.idref).select(*args)


def get_workitem(v1, number, *args):
    """Get a workitem or die trying.
       args are passed to select to pre-populate fields
    """
    try:
        return v1.Workitem.where(Number=number).select(*args).first()
    except IndexError:
        raise QuitNow('I\'m sorry {{nick}}, item "{0}" not found'.format(number))


def get_user(v1, nick):
    o_nick = nick
    try:
        nick = db.v1_user_map.find_one({'irc_nick': nick})['v1_nick']
    except (TypeError, KeyError):
        # Lookup failed, no worries
        pass

    try:
        return v1.Member.filter(
            "Name='{0}'|Nickname='{0}'|Username='{0}'".format(nick)
        ).select(
            'Name', 'Nickname'
        ).first()
    except IndexError:
        raise QuitNow(
            'I\'m sorry {{nick}}, couldn\'t find {0} in VersionOne as {1}. '
            'Check !v1 alias'.format(o_nick, nick)
        )


def get_creds(nick):
    """returns simple token as string, OAuth2Credentials instance, or None
    """

    auth_info = db.v1_oauth.find_one({'irc_nick': nick}) or None
    # Try to trim nick for usual things
    if auth_info is None:
        if '|' in nick:
            nick = nick.split('|', 1)[0].strip()
        elif '_' in nick:
            nick = nick.split('_', 1)[0].strip()
        auth_info = db.v1_oauth.find_one({'irc_nick': nick}) or {}

    token = auth_info.get('api_token')
    if token:
        return token

    if USE_OAUTH:
        try:
            return OAuth2Credentials(
                auth_info['access_token'],
                settings.VERSIONONE_OAUTH_CLIENT_ID,
                settings.VERSIONONE_OAUTH_CLIENT_SECRET,
                auth_info['refresh_token'],
                auth_info['token_expiry'],
                settings.VERSIONONE_URL + '/oauth.v1/token',
                'helga (chatbot)',
            )
        except Exception:
            # TODO - what can get raised here
            logger.warning('Problem getting OAuth creds for {0}'.format(nick), exc_info=True)
            raise QuitNow('Sorry {{nick}}, couldn\'t get OAuth creds for you, try "!v1 oauth"')

    return None


@deferred_to_channel
def alias_command(v1, client, channel, nick, *args):
    # Populate subcmd, and target to continue
    target = nick
    try:
        subcmd = args[0]
        args = args[1:]
    except IndexError:
        # 0 args lookup nick
        subcmd = 'lookup'
    else:
        # At least 1 arg
        if args:
            target = ' '.join(args)
        else:
            # Exactly 1 arg - look it up if not a command
            if subcmd not in ['lookup', 'remove']:
                target = subcmd
                subcmd = 'lookup'

    if subcmd == 'lookup':
        lookup = {'irc_nick': target}
        try:
            v1_nick = db.v1_user_map.find_one(lookup)['v1_nick']
        except (TypeError, KeyError):
            v1_nick = target
        return '{0} is known as {1} in V1'.format(target, v1_nick)

    elif subcmd == 'set':
        lookup = {'irc_nick': nick}
        alias = db.v1_user_map.find_one(lookup) or lookup
        alias['v1_nick'] = target
        db.v1_user_map.save(alias)

    elif subcmd == 'remove':
        if target != nick:
            return 'That\'s not nice {0}. You can\'t remove {1}'.format(nick, target)
        lookup = {'irc_nick': nick}
        db.v1_user_map.find_and_modify(lookup, remove=True)
    else:
        return 'No {0}, you can\'t {1}!'.format(nick, subcmd)

    return random_ack()


@deferred_to_nick
def token_command(v1, client, channel, nick, reply_code=None):
    if reply_code:
        q = {'irc_nick': nick}
        auth_info = db.v1_oauth.find_one(q) or q

        if reply_code == 'forget':
            # remove the token
            try:
                del(auth_info['api_token'])
            except KeyError:
                return 'Token was already gone'
        else:
            # update the token
            auth_info['api_token'] = reply_code
        db.v1_oauth.save(auth_info)
        return random_ack()

    # No reply_code - show step1 instructions
    return (
        'In V1 go to your Applications and generate a Personal Access Token'
        'then do "!v1 token <code>" with the generated code'
    )


@deferred_to_nick
def oauth_command(v1, client, channel, nick, reply_code=None):
    if not USE_OAUTH:
        return 'Oauth is not enabled'

    client = OAuth2WebServerFlow(
        settings.VERSIONONE_OAUTH_CLIENT_ID,
        settings.VERSIONONE_OAUTH_CLIENT_SECRET,
        'apiv1',  # Scope for XML api
        redirect_uri='urn:ietf:wg:oauth:2.0:oob',
        auth_uri=settings.VERSIONONE_URL + '/oauth.v1/auth',
        token_uri=settings.VERSIONONE_URL + '/oauth.v1/token',
    )

    if reply_code:
        q = {'irc_nick': nick}
        auth_info = db.v1_oauth.find_one(q) or q

        if reply_code == 'forget':
            for key in ['access_token', 'refresh_token', 'token_expiry']:
                try:
                    del(auth_info[key])
                except KeyError:
                    pass
        else:
            try:
                creds = client.step2_exchange(reply_code)
            except FlowExchangeError as e:
                return 'Sorry {0} "{1}" happened. Try "!v1 oauth" again from the start'.format(nick, e)

            # Creds Ok, save the info
            auth_info['access_token'] = creds.access_token
            auth_info['refresh_token'] = creds.refresh_token
            auth_info['token_expiry'] = creds.token_expiry

        db.v1_oauth.save(auth_info)
        return random_ack()

    # No reply_code - show step1 link
    return 'Visit {0} then do "!v1 oauth <code>" with the generated code'.format(
        client.step1_get_authorize_url())


def get_v1(nick):
    """Get the v1 connection"""

    try:
        credentials = get_creds(nick)

        # Access Token is prefered, remove token to use OAUTH
        if isinstance(credentials, basestring):
            v1 = V1Meta(
                instance_url=settings.VERSIONONE_URL,
                password=credentials,
                use_password_as_token=True,
            )

        # Use Oauth if provided
        elif credentials:
            v1 = V1Meta(
                instance_url=settings.VERSIONONE_URL,
                credentials=credentials,
            )

        # System user if no creds
        else:
            # Too much overhead, don't really need to re-init every call
            v1 = V1Meta(
                instance_url=settings.VERSIONONE_URL,
                username=settings.VERSIONONE_AUTH[0],
                password=settings.VERSIONONE_AUTH[1],
            )

    except AttributeError:
        logger.error('VersionOne plugin misconfigured, check your settings')
        raise

    return v1


def _get_review(item):
    for field in settings.VERSIONONE_CR_FIELDS:
        try:
            val = getattr(item, field)
            return '' if val is None else val, field
        except AttributeError:
            pass
    # No candidate fields matched, number might not have been a valid type
    raise NotFound


@deferred_to_channel
def review_command(v1, client, channel, nick, number, *args):
    """(review | cr) <issue> [!]<text>
       With no text, show review link
       With '!' before text replace link, otherwise append
    """

    w = get_workitem(v1, number)

    try:
        link, field = _get_review(w)
    except NotFound:
        # No candidate fields matched, number might not have been valid
        return 'I\'m sorry {0}, item "{1}" doesn\'t support reviews'.format(nick, number)

    if args is ():
        return '{0} Reviews: {1}'.format(number, link or '(None)')

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
        return commit_changes(v1, (w, field, new_link),)

    return 'Already got that one {0}'.format(nick)


@deferred_to_channel
def team_command(v1, client, channel, nick, *args):
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
            team = v1.Team.where(Name=name).first()
        except IndexError:
            return 'I\'m sorry {0}, team name "{1}" not found'.format(nick, name)
        # Manually building a url is lame, but the url property on TeamRooms doesn't work
        teams[name] = ', '.join([
            '{0}/TeamRoom.mvc/Show/{1}'.format(settings.VERSIONONE_URL, r.intid) for r in team.Rooms
        ]) or team.url
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


@deferred_to_channel
def take_command(v1, client, channel, nick, number):
    w = get_workitem(v1, number, 'Owners')
    user = get_user(v1, nick)

    if user in w.Owners:
        return 'Dude {0}, you already own it!'.format(nick)
    # Writing to Owners can only add values
    return commit_changes(v1, (w, 'Owners', [user]))


def _list_or_add_things(v1, class_name, number, action=None, *args):
    Klass = getattr(v1, class_name)
    workitem = get_workitem(v1, number)
    if action is None:
        things = list(_get_things(Klass, workitem))
        things.sort(key=lambda t: t.Status.Order)

        return '\n'.join([
            '[{0}] {1} {2}'.format(t.Status.Name, t.Name, t.url)
            for t in things
        ]) if things else 'Didn\'t find any {0}s for {1}'.format(class_name, number)

    if action != u'add':
        raise QuitNow('I can\'t just "{0}" that, {{nick}}'.format(action))

    name = ' '.join(args)

    if not name:
        raise QuitNow('I\'m going to need a title for that, {nick}')

    t = create_object(
        Klass,
        Name=name,
        Parent=workitem.idref,
    )

    raise QuitNow('I created {0} {1} for you, {{nick}}'.format(t.Name, t.url))


@deferred_to_channel
def tasks_command(v1, client, channel, nick, number, action=None, *args):
    return _list_or_add_things(v1, 'Task', number, action, *args)


@deferred_to_channel
def tests_command(v1, client, channel, nick, number, action=None, *args):
    return _list_or_add_things(v1, 'Test', number, action, *args)


@deferred_to_channel
def user_command(v1, client, channel, nick, *args):
    # Recombine space'd args for full name lookup
    lookup = ' '.join(args) or nick
    user = get_user(v1, lookup)
    return '{0} [{1}] ({2})'.format(user.Name, user.Nickname, user.url)


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


def versionone_command(v1, client, channel, nick, message, cmd, args):
    """
    Command handler for the versionone plugin
    """
    try:
        subcmd = args.pop(0)
    except IndexError:
        return [
            'Usage for versionone (alias v1)',
            '!v1 alias [lookup | set | remove] - Lookup an alias, or set/remove your own',
            '!v1 oauth [<code> | forget] - Configure or remove your oauth tokens',
            '!v1 review <issue> [!]<text> - Lookup, append, or set codereview field (alias: cr)',
            '!v1 take <ticket-id> - Add yourself to the ticket\'s Owners',
            '!v1 tasks <ticket-id> (add <title>) - List tasks for ticket, or add one',
            '!v1 team[s] [add | remove | list] <teamname> -- add, remove, list team(s) for the channel',
            '!v1 tests <ticket-id> (add <title>) - List tests for ticket, or add one',
            '!v1 token [<code> | forget] - Configure or remove your v1 API token',
            '!v1 user <nick> - Lookup V1 user for an ircnick',
        ]
    logger.debug('Calling VersionOne subcommand {0} with args {1}'.format(subcmd, args))

    try:
        return COMMAND_MAP[subcmd](v1, client, channel, nick, *args)
    except KeyError:
        return u'Umm... {0}, Never heard of it?'.format(subcmd)
    except TypeError:
        # can only be reached by a command that doesn't use the deffered_to_* wrapper
        return u'Umm... {0}, you might want to check the docs for {1}'.format(nick, subcmd)


@deferred_to_channel
def versionone_full_descriptions(v1, client, channel, nick, message, matches):
    """
    Meant to be run asynchronously because it uses the network
    """
    specials = defaultdict(list)

    for m in matches:
        # Build lists of special lookup types
        kind = m.split('-')[0]
        if kind in SPECIAL_PATTERNS:
            specials[SPECIAL_PATTERNS[kind]].append(m)
        else:
            # Or default to Workitem
            specials['Workitem'].append(m)

    descriptions = []
    for kind, vals in specials.items():
        descriptions += [
            u'[{number}] {name} ({url})'.format(**{
                'name': s.Name,
                'number': s.Number,
                'url': s.url,
            })
            # Use the right Endpoint
            for s in getattr(v1, kind).filter(
                # OR join on each number
                '|'.join(["Number='{0}'".format(n) for n in vals])
            ).select('Name', 'Number')
        ]

    return '\n'.join(descriptions)


@match(find_versionone_numbers)
@command('versionone', aliases=['v1'], help='Interact with VersionOne tickets.'
         'Usage: "!v1" for help')
def versionone(client, channel, nick, message, *args):
    """
    A plugin for showing URLs to VERSIONONE ticket numbers. This is both a set of commands to
    interact with tickets, and a match to automatically show them.

    Issue numbers are automatically detected.
    """

    try:
        v1 = get_v1(nick)
    except QuitNow:
        # With OAUTH, get_creds can raise QuitNow
        logger.warning('No v1 connection for {0}'.format(nick))
        v1 = None

    if len(args) == 2:
        # args = [cmd, args]
        fn = versionone_command
    else:
        # args = [matches]
        fn = versionone_full_descriptions
    res = fn(v1, client, channel, nick, message, *args)

    if isinstance(res, Deferred):
        raise ResponseNotReady
    return res


COMMAND_MAP = {
    'alias': alias_command,
    'cr': review_command,
    'oauth': oauth_command,
    'review': review_command,
    'take': take_command,
    'tasks': tasks_command,
    'team': team_command,
    'teams': team_command,
    'tests': tests_command,
    'token': token_command,
    'user': user_command,
}
