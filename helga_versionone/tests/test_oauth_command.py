from mock import call, patch
from pretend import stub

from oauth2client.client import FlowExchangeError

from .util import V1TestCase


class TestOauthCommandDisabled(V1TestCase):
    def test_disabled(self):
        self.USE_OAUTH = False

        return self._test_command(
            'oauth',
            'Oauth is not enabled',
            to_nick=True,
        )


class TestOauthCommand(V1TestCase):
    USE_OAUTH = patch('helga_versionone.USE_OAUTH', True)
    OAuth2WebServerFlow = patch('helga_versionone.OAuth2WebServerFlow')

    def test_get_code(self):
        url = 'http://example.com'
        self.OAuth2WebServerFlow().step1_get_authorize_url.return_value = url

        return self._test_command(
            'oauth',
            'Visit {0} then do "!v1 oauth <code>" with the generated code'.format(url),
            to_nick=True,
        )

    def test_reply_server_fail(self):
        msg = 'Whut!'
        self.OAuth2WebServerFlow().step2_exchange.side_effect = FlowExchangeError(msg)

        return self._test_command(
            'oauth somebiglongoauthreturncode',
            'Sorry {0} "{1}" happened. Try "!v1 oauth" again from the start'.format(
                self.nick, msg),
            to_nick=True,
        )

    def test_reply_ok(self):
        auth_info = {}
        auth_info['access_token'] = 'this is my token'
        auth_info['refresh_token'] = 'a refresh token'
        auth_info['token_expiry'] = 'sometime tomorrow'

        # No existing user
        self.db.v1_oauth.find_one.return_value = {}

        # Usable creds from Oauth
        self.OAuth2WebServerFlow().step2_exchange.return_value = stub(**auth_info)

        d = self._test_command(
            'oauth somebiglongoauthreturncode',
        )

        def check(res):
            # assertDictContainsSubset would be super cool, but it's a 2.7 feature
            # and we know what will be here
            auth_info.update({'irc_nick': self.nick})
            self.assertEqual(self.db.v1_oauth.save.call_args, call(auth_info))
            self.assertAck()

        d.addCallback(check)
        return d
