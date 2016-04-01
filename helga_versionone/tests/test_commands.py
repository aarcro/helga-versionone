from mock import MagicMock, patch
from pretend import stub

import helga_versionone

from .util import V1TestCase


class TestCommands(V1TestCase):
    def test_no_patching(self):
        # settings are patched
        from helga_versionone import settings
        assert settings.VERSIONONE_URL == 'https://www.example.com/EnvKey'

    def test_patching(self):
        # settings can be overridden
        self.settings.VERSIONONE_URL = 'tada'
        assert helga_versionone.settings.VERSIONONE_URL == 'tada'

    def test_bad_command(self):
        return self._test_command('notreal', u'Umm... notreal, Never heard of it?')

    def test_get_workitem_found(self):
        self.v1.Workitem.where().select().first.return_value = 'foo'
        f = helga_versionone.get_workitem(self.v1, 'B-00010')
        self.assertEquals(f, 'foo')

    def test_get_workitem_not_found(self):
        self.v1.Workitem.where.side_effect = IndexError
        self.assertRaises(helga_versionone.QuitNow, helga_versionone.get_workitem, self.v1, 'B-00010')

    def test_get_user_found(self):
        self.v1.Member.filter().select().first.return_value = 'foo'
        u = helga_versionone.get_user(self.v1, self.nick)
        self.assertEquals(u, 'foo')

    def test_get_user_not_found(self):
        self.v1.Member.filter.side_effect = IndexError
        self.assertRaises(helga_versionone.QuitNow, helga_versionone.get_user, self.v1, self.nick)

    def test_get_user_with_no_alias(self):
        self.db.v1_user_map.find_one.side_effect = KeyError
        self.v1.Member.filter().select().first.return_value = 'foo'
        u = helga_versionone.get_user(self.v1, self.nick)
        self.assertEquals(u, 'foo')

    @patch('helga_versionone.OAuth2Credentials')
    @patch('helga_versionone.USE_OAUTH')
    def _test_get_creds(self, name, mock_USE_OAUTH, mock_OAuth2Credentials, oauth_works=False, token_works=True):
        # First call should fail, so nick re-writing happens
        # Second needs keys for the call to OAuth2Credentials
        auth_info = {}
        mock_USE_OAUTH = False

        if oauth_works:
            mock_USE_OAUTH = True
            auth_info['access_token'] = 'asdf'
            auth_info['refresh_token'] = 'asdf'
            auth_info['token_expiry'] = 'asdf'

        if token_works:
            auth_info['api_token'] = 'mahtoken'

        self.db.v1_oauth.find_one.side_effect = [None, auth_info]
        if oauth_works:
            mock_OAuth2Credentials.return_value = 'foo'
        else:
            mock_OAuth2Credentials.side_effect = KeyError

        if oauth_works and not token_works:
            c = helga_versionone.get_creds(name)
            self.assertEquals(c, 'foo')
        elif token_works:
            c = helga_versionone.get_creds(name)
            self.assertEquals(c, 'mahtoken')
        else:
            self.assertRaises(helga_versionone.QuitNow, helga_versionone.get_creds, name)

    def test_get_creds_plain(self):
        self._test_get_creds('somename')

    def test_get_creds_underscore(self):
        # No pipe - split underscore
        self._test_get_creds('somename_away')
        self.db.v1_oauth.find_one.called_with({'irc_nick': 'somename'})

    def test_get_creds_pipe(self):
        # With pipe - split pipe only
        self._test_get_creds('some_name|away')
        self.db.v1_oauth.find_one.called_with({'irc_nick': 'some_name'})

    def test_get_creds_oauth_works(self):
        self._test_get_creds('fhqwhgads', oauth_works=True, token_works=False)

    def test_get_creds_fail_all(self):
        self._test_get_creds('fhqwhgads', oauth_works=False, token_works=False)

    def test_find_all(self):
        numbers = helga_versionone.find_versionone_numbers('Tell me about B-0010')
        self.assertEquals(numbers, ['B-0010'])

    def test_usage(self):
        res = self._test_command('')
        self.assertIn('Usage for versionone', res[0])

    def test_bad_arg_count(self):
        return self._test_command(
            'take',
            u'Umm... {0}, you might want to check the docs for that'.format(self.nick),
        )

    @patch('helga_versionone.versionone_full_descriptions')
    def test_plugin_match(self, fn):
        msg = 'Tell me about B-0010',
        matches = ['B-0010']
        helga_versionone.versionone(
            self.client,
            self.channel,
            self.nick,
            msg,
            matches,
        )

        fn.assert_called_once_with(
            self.v1,
            self.client,
            self.channel,
            self.nick,
            msg,
            matches,
        )

    @patch('helga_versionone.versionone_command')
    def test_plugin_subcommand(self, fn):
        # QuitNow doesn't stop processing of command
        self.get_v1.side_effect = helga_versionone.QuitNow()

        msg = '!v1 teams'
        cmd = '!v1'
        args = ['teams']

        helga_versionone.versionone(
            self.client,
            self.channel,
            self.nick,
            msg,
            cmd,
            args,
        )

        fn.assert_called_once_with(
            None,
            self.client,
            self.channel,
            self.nick,
            msg,
            cmd,
            args,
        )

    def test_no_v1_for_command(self):
        self.v1 = None
        # For coverage, hit bad_args with v1 == None
        return self._test_command(
            'tasks B-0010 fhqwhgads',
            u'{0}, you might want to try "!v1 oauth" or "!v1 token"'.format(self.nick),
        )

    def test_versionone_full_descriptions(self):
        w = stub(
            Name='Issue name',
            Number='B-0010',
            url='http://example.com',
        )
        self.v1.Workitem.filter().select.return_value = [w]

        d = helga_versionone.versionone_full_descriptions(
            self.v1,
            self.client,
            self.channel,
            self.nick,
            'Something about B-0010',
            ['B-0010'],
        )

        def check(res):
            self.client.msg.assert_called_once_with(
                self.channel,
                '[{number}] {name} ({url})'.format(**{
                    'name': w.Name,
                    'number': w.Number,
                    'url': w.url,
                })
            )

        d.addCallback(check)
        return d

    def test_versionone_full_descriptions_special(self):
        w = stub(
            Name='Issue name',
            Number='I-0010',
            url='http://example.com',
        )
        self.v1.Issue.filter().select.return_value = [w]

        d = helga_versionone.versionone_full_descriptions(
            self.v1,
            self.client,
            self.channel,
            self.nick,
            'Something about I-0010',
            ['I-0010'],
        )

        def check(res):
            self.client.msg.assert_called_once_with(
                self.channel,
                '[{number}] {name} ({url})'.format(**{
                    'name': w.Name,
                    'number': w.Number,
                    'url': w.url,
                })
            )

        d.addCallback(check)
        return d


class TestUserCommand(V1TestCase):
    get_user = patch('helga_versionone.get_user', return_value=stub(
        Name='fhqwhgads',
        Nickname='joe',
        url='http://example.com',
    ))

    def test_user_default_command(self):
        d = self._test_command(
            'user',
            'fhqwhgads [joe] (http://example.com)',
        )

        def check(res):
            self.get_user.assert_called_once_with(self.v1, self.nick)

        d.addCallback(check)
        return d

    def test_user_explicit_command(self):
        d = self._test_command(
            'user fhqwhgads',
            'fhqwhgads [joe] (http://example.com)',
        )

        def check(res):
            self.get_user.assert_called_once_with(self.v1, 'fhqwhgads')

        d.addCallback(check)
        return d
