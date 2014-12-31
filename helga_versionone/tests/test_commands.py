from functools import wraps
from mock import MagicMock, call, patch
from pretend import stub
from twisted.internet.defer import Deferred
from twisted.trial import unittest

import helga_versionone
from helga.plugins import ACKS

settings_stub = stub(
    VERSIONONE_URL='https://www.example.com/EnvKey',
    VERSIONONE_AUTH=('username', 'password'),
    VERSIONONE_CR_FIELDS=('field_one', 'field_two'),
    VERSIONONE_READONLY=True,
    VERSIONONE_OAUTH_ENABLED=False,
    VERSIONONE_OAUTH_CLIENT_ID='client_id',
    VERSIONONE_OAUTH_CLIENT_SECRET='client_secret',
)


class deferred_patch(object):
    """Patches target until the deferred returns, appends patched object to args"""
    def __init__(self, target):
        self.patcher = patch(target)

    def __call__(self, fn):
        @wraps(fn)
        def inner(herself, *args, **kwargs):
            p = self.patcher.start()
            args = list(args)
            args.append(p)
            # patcher.stop() is always None, so return res, don't eat it (allows failures to propagate)
            return fn(herself, *args, **kwargs).addBoth(lambda res: self.patcher.stop() or res)

        return inner


def stop_patches(fn):
    @wraps(fn)
    def inner(self, *args, **kwargs):
        res = fn(self, *args, **kwargs)
        if isinstance(res, Deferred):
            # clearPatches() is always None, so return x, don't eat it (allows failures to propagate)
            return res.addBoth(lambda x: self.clearPatches() or x)
        # Not deferred, stop patches and return
        self.clearPatches()
        return res
    return inner


class V1TestCaseMeta(type):
    def __new__(meta, name, bases, dct):
        """Decorate all test methods in dct"""
        for fn_name, fn in dct.iteritems():
            # Named test* and is a method
            if fn_name.startswith('test') and callable(fn):
                dct[fn_name] = stop_patches(fn)

        return super(V1TestCaseMeta, meta).__new__(meta, name, bases, dct)


class V1TestCase(unittest.TestCase):
    """Base class for all helga_versionone tests
       get_v1 is always patched to return self.v1 - a MagicMock()
       helga_versionone.settings is always patched
       helga_versionone.db is always patched
    """
    __metaclass__ = V1TestCaseMeta

    nick = 'me'
    channel = '#bots'

    # Keys from patches will be attrs on TestCase instances
    # Freely change them in each test, they will be cleaned up
    # after sync return or deferred callback

    patches = {
        'db': ['helga_versionone.db'],
        'settings': ['helga_versionone.settings', settings_stub],
        'get_v1': ['helga_versionone.get_v1'],
    }

    def setUp(self):
        # Before each test, start the patches
        # metaclass has decorated the test methods to call clearPatches
        for attr, args in self.patches.iteritems():
            patcher = patch(*args)
            setattr(self, '_{0}_patcher'.format(attr), patcher)
            setattr(self, attr, patcher.start())

        self.v1 = MagicMock()
        # Depends on "get_v1" being in patches above
        self.get_v1.return_value = self.v1

        # client is mocked, but doesn't have to be patched.
        self.client = MagicMock()
        super(V1TestCase, self).setUp()

    def clearPatches(self):
        for p in self.patches.keys():
            getattr(self, '_{0}_patcher'.format(p)).stop()

    def assertAck(self):
        self.assertIn(self.client.msg.call_args[0][1], ACKS)

    def _test_command(self, cmd, expected=None):
        """Test a version command: !v1 <cmd>"""
        d = helga_versionone.versionone_command(
            self.v1,
            self.client,
            self.channel,
            self.nick,
            'unused message',
            'unused cmd',
            cmd.split(),
        )

        if expected is None:
            return d

        if isinstance(d, Deferred):
            def check(actual):
                self.assertEqual(call(self.channel, expected), self.client.msg.call_args)

            d.addCallback(check)
            return d
        else:
            self.assertEqual(d, expected)


class TestCommands(V1TestCase):

    def test_no_patching(self):
        # settings can be overridded
        from helga_versionone import settings
        assert settings.VERSIONONE_URL == 'https://www.example.com/EnvKey'

    def test_patching(self):
        # settings can be overridden
        self.settings.VERSIONONE_URL = 'tada'
        assert helga_versionone.settings.VERSIONONE_URL == 'tada'

    def test_bad_command(self):
        return self._test_command('notreal', u'Umm... notreal, Never heard of it?')

    def test_no_teams(self):
        self.db.v1_channel_settings.find_one.return_value = None
        return self._test_command('teams', u'No teams found for {0}'.format(self.channel))

    def test_teams(self):
        self.db.v1_channel_settings.find_one.return_value = {'teams': {'teamName': 'link'}}
        return self._test_command('teams', u'teamName link')

    def test_team_add_fail(self):
        self.v1.Team.where.side_effect = IndexError
        return self._test_command(
            'teams add not there',
            u'I\'m sorry {0}, team name "not there" not found'.format(self.nick),
        )

    def test_team_add_ok_url(self):
        self.db.v1_channel_settings.find_one.return_value = None
        team = MagicMock()
        team.url = 'http://example.com/'
        team.Rooms = []
        self.v1.Team.where().first.return_value = team
        d = self._test_command(
            'teams add team name',
        )

        def check(res):
            # call_args[0] ==> *args
            self.assertEqual(self.db.v1_channel_settings.save.call_args[0][0]['teams']['team name'], team.url)
            self.assertAck()

        d.addCallback(check)
        return d

    def test_team_add_ok_rooms(self):
        # Needs settings patched through deferred
        self.db.v1_channel_settings.find_one.return_value = None
        team = MagicMock()
        team.Rooms = [stub(intid=3)]
        self.v1.Team.where().first.return_value = team
        d = self._test_command(
            'teams add team name',
        )

        def check(res):
            self.assertEqual(
                self.db.v1_channel_settings.save.call_args[0][0]['teams']['team name'],
                '{0}/TeamRoom.mvc/Show/3'.format(settings_stub.VERSIONONE_URL),
            )
            self.assertAck()

        d.addCallback(check)
        return d

    def test_team_remove_fail(self):
        self.db.v1_channel_settings.find_one.return_value = None
        return self._test_command(
            'team remove team name',
            'I\'m sorry {0}, team name "team name" not found for {1}'.format(self.nick, self.channel),
        )

    def test_team_remove_ok(self):
        self.db.v1_channel_settings.find_one().get.return_value = {'this one': 'http://example.com'}
        d = self._test_command(
            'team remove this one',
        )

        d.addCallback(lambda _: self.assertAck())
        return d

    def test_team_no_command(self):
        return self._test_command(
            'team naugty',
            'No {0}, you can\'t naugty!'.format(self.nick),
        )
