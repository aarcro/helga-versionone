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
