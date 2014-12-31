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

settings_patcher = patch('helga_versionone.settings', settings_stub)
# This is aweful, but it needs to be in effect while deferreds run
# Need a meta class to add a deferred_patch to all test commands :(
settings_stub = settings_patcher.start()

# TODO - db should also always be patched


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


class TestCommands(unittest.TestCase):
    nick = 'me'
    channel = '#bots'

    def setUp(self):
        self.client = MagicMock()
        self.v1_patcher = patch('helga_versionone.get_v1')
        self.v1 = MagicMock()
        self.get_v1 = self.v1_patcher.start()
        self.get_v1.return_value = self.v1

    def tearDown(self):
        self.v1_patcher.stop()

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

    def test_no_patching(self):
        # settings can be overridded
        from helga_versionone import settings
        assert settings.VERSIONONE_URL == 'https://www.example.com/EnvKey'

    @patch.dict(settings_stub.__dict__, VERSIONONE_URL='tada')
    def test_patching(self):
        # settings can be overridden
        assert helga_versionone.settings.VERSIONONE_URL == 'tada'

    def test_bad_command(self):
        return self._test_command('notreal', u'Umm... notreal, Never heard of it?')

    @deferred_patch('helga_versionone.db')
    def test_no_teams(self, db):
        db.v1_channel_settings.find_one.return_value = None
        return self._test_command('teams', u'No teams found for {0}'.format(self.channel))

    @deferred_patch('helga_versionone.db')
    def test_teams(self, db):
        db.v1_channel_settings.find_one.return_value = {'teams': {'teamName': 'link'}}
        return self._test_command('teams', u'teamName link')

    def test_team_add_fail(self):
        self.v1.Team.where.side_effect = IndexError
        return self._test_command(
            'teams add not there',
            u'I\'m sorry {0}, team name "not there" not found'.format(self.nick),
        )

    @deferred_patch('helga_versionone.db')
    def test_team_add_ok_url(self, db):
        db.v1_channel_settings.find_one.return_value = None
        team = MagicMock()
        team.url = 'http://example.com/'
        team.Rooms = []
        self.v1.Team.where().first.return_value = team
        d = self._test_command(
            'teams add team name',
        )

        def check(res):
            # call_args[0] ==> *args
            self.assertEqual(db.v1_channel_settings.save.call_args[0][0]['teams']['team name'], team.url)
            self.assertAck()

        d.addCallback(check)
        return d

    @deferred_patch('helga_versionone.db')
    def test_team_add_ok_rooms(self, db):
        # Needs settings patched through deferred
        db.v1_channel_settings.find_one.return_value = None
        team = MagicMock()
        team.Rooms = [stub(intid=3)]
        self.v1.Team.where().first.return_value = team
        d = self._test_command(
            'teams add team name',
        )

        def check(res):
            self.assertEqual(
                db.v1_channel_settings.save.call_args[0][0]['teams']['team name'],
                '{0}/TeamRoom.mvc/Show/3'.format(settings_stub.VERSIONONE_URL),
            )
            self.assertAck()

        d.addCallback(check)
        return d

    @deferred_patch('helga_versionone.db')
    def test_team_remove_fail(self, db):
        db.v1_channel_settings.find_one.return_value = None
        return self._test_command(
            'team remove team name',
            'I\'m sorry {0}, team name "team name" not found for {1}'.format(self.nick, self.channel),
        )

    @deferred_patch('helga_versionone.db')
    def test_team_remove_ok(self, db):
        db.v1_channel_settings.find_one().get.return_value = {'this one': 'http://example.com'}
        d = self._test_command(
            'team remove this one',
        )

        d.addCallback(lambda _: self.assertAck())
        return d

    @deferred_patch('helga_versionone.db')
    def test_team_no_command(self, db):
        return self._test_command(
            'team naugty',
            'No {0}, you can\'t naugty!'.format(self.nick),
        )
