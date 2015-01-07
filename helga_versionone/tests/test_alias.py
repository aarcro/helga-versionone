from mock import call

from .util import V1TestCase


class TestAliasCommand(V1TestCase):
    def test_no_args_no_match(self):
        # v1_nick = db.v1_user_map.find_one(lookup)['v1_nick']
        self.db.v1_user_map.find_one.return_value = {}
        return self._test_command(
            'alias',
            '{0} is known as {1} in V1'.format(self.nick, self.nick),
        )

    def test_lookup_no_match(self):
        # v1_nick = db.v1_user_map.find_one(lookup)['v1_nick']
        self.db.v1_user_map.find_one.return_value = {}
        return self._test_command(
            'alias lookup',
            '{0} is known as {1} in V1'.format(self.nick, self.nick),
        )

    def test_no_args_match(self):
        # v1_nick = db.v1_user_map.find_one(lookup)['v1_nick']
        self.db.v1_user_map.find_one.return_value = {'v1_nick': 'nickname'}
        return self._test_command(
            'alias',
            '{0} is known as nickname in V1'.format(self.nick),
        )

    def test_lookup_match(self):
        # v1_nick = db.v1_user_map.find_one(lookup)['v1_nick']
        self.db.v1_user_map.find_one.return_value = {'v1_nick': 'nickname'}
        return self._test_command(
            'alias lookup',
            '{0} is known as nickname in V1'.format(self.nick),
        )

    def test_lookup_is_default(self):
        # v1_nick = db.v1_user_map.find_one(lookup)['v1_nick']
        self.db.v1_user_map.find_one.return_value = {}
        return self._test_command(
            'alias fhqwhgads',
            'fhqwhgads is known as fhqwhgads in V1',
        )

    def test_lookup_other__no_match(self):
        # v1_nick = db.v1_user_map.find_one(lookup)['v1_nick']
        self.db.v1_user_map.find_one.return_value = {}
        return self._test_command(
            'alias lookup fhqwhgads',
            'fhqwhgads is known as fhqwhgads in V1',
        )

    def test_lookup_other_match(self):
        # v1_nick = db.v1_user_map.find_one(lookup)['v1_nick']
        self.db.v1_user_map.find_one.return_value = {'v1_nick': 'nickname'}
        return self._test_command(
            'alias lookup fhqwhgads',
            'fhqwhgads is known as nickname in V1',
        )

    def test_set(self):
        # alias = db.v1_user_map.find_one(lookup) or lookup
        # db.v1_user_map.save(alias)
        self.db.v1_user_map.find_one.return_value = None

        d = self._test_command(
            'alias set fhqwhgads',
        )

        def check(res):
            self.assertEquals(
                self.db.v1_user_map.save.call_args,
                call({'irc_nick': self.nick, 'v1_nick': 'fhqwhgads'}),
            )
            self.assertAck()

        d.addCallback(check)
        return d

    def test_remove_implicit_ok(self):
        # alias = db.v1_user_map.find_one(lookup) or lookup
        self.db.v1_user_map.find_one.return_value = None

        d = self._test_command(
            'alias remove',
        )

        def check(res):
            self.assertEquals(
                self.db.v1_user_map.find_and_modify.call_args,
                call({'irc_nick': self.nick}, remove=True),
            )
            self.assertAck()

        d.addCallback(check)
        return d

    def test_remove_explicit_ok(self):
        # alias = db.v1_user_map.find_one(lookup) or lookup
        self.db.v1_user_map.find_one.return_value = None

        d = self._test_command(
            'alias remove {0}'.format(self.nick),
        )

        def check(res):
            self.assertEquals(
                self.db.v1_user_map.find_and_modify.call_args,
                call({'irc_nick': self.nick}, remove=True),
            )
            self.assertAck()

        d.addCallback(check)
        return d

    def test_remove_explicit_fail(self):
        return self._test_command(
            'alias remove fhqwhgads',
            'That\'s not nice {0}. You can\'t remove fhqwhgads'.format(self.nick)
        )

    def test_no_command(self):
        return self._test_command(
            'alias naughty fhqwhgads'
            'No {0}, you can\'t naughty!'.format(self.nick)
        )
