from mock import MagicMock
from pretend import stub

from .util import V1TestCase


class TestTeamCommand(V1TestCase):
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
                '{0}/TeamRoom.mvc/Show/3'.format(self.settings.VERSIONONE_URL),
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
