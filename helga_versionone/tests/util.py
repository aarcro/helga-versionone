import logging

from copy import copy
from functools import wraps
from mock import MagicMock, patch
from mock.mock import _patch as Patch
from pretend import stub
from twisted.internet.defer import Deferred
from twisted.trial import unittest

import helga_versionone
from helga.plugins import ACKS


logger = logging.getLogger(__name__)
settings_stub = stub(
    VERSIONONE_URL='https://www.example.com/EnvKey',
    VERSIONONE_AUTH=('username', 'password'),
    VERSIONONE_CR_FIELDS=('field_one', 'field_two'),
    VERSIONONE_READONLY=True,
    VERSIONONE_OAUTH_ENABLED=False,
    VERSIONONE_OAUTH_CLIENT_ID='client_id',
    VERSIONONE_OAUTH_CLIENT_SECRET='client_secret',
)

writeable_settings_stub = copy(settings_stub)
writeable_settings_stub.VERSIONONE_READONLY = False


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


class PatchedTestCaseMeta(type):
    def __new__(meta, name, bases, dct):
        """Decorate all test methods in dct"""

        for k, v in dct.iteritems():
            # Named test* and is a method
            if k.startswith('test') and callable(v):
                logger.debug('decorate {0} -> {1} for {2}'.format(k, v, meta))
                # Then decorate with the stopper
                dct[k] = stop_patches(v)
                dct[k].__patched = True

        return super(PatchedTestCaseMeta, meta).__new__(meta, name, bases, dct)

    def __init__(cls, name, bases, dct):
        """Collect patches"""
        if hasattr(cls, '_mock_patches'):
            # This must be from a base class,
            # copy it so it doesn't get mutated in the base
            cls._mock_patches = copy(cls._mock_patches)
        else:
            cls._mock_patches = set()

        for k, v in dct.iteritems():
            if isinstance(v, Patch):
                # If it's a patch add it to patches
                logger.debug('Adding {0} patch to {1}'.format(k, cls))
                cls._mock_patches.add(k)

        return super(PatchedTestCaseMeta, cls).__init__(name, bases, dct)


class PatchedTestCase(unittest.TestCase):
    """class properties which are mock._patch instances (returned by mock.patch) will become
       instance variables which are the mock object.

       patches are started in setUp

       patches are stopped when testMethod completes, either normally or through a deferred
    """

    __metaclass__ = PatchedTestCaseMeta

    def setUp(self):
        # Before each test, start the patches
        # metaclass has decorated the test methods to call clearPatches
        for attr in self._mock_patches:
            patcher = getattr(self, attr)
            setattr(self, '_{0}_patcher'.format(attr), patcher)
            setattr(self, attr, patcher.start())

        super(PatchedTestCase, self).setUp()

    def clearPatches(self):
        for p in self._mock_patches:
            getattr(self, '_{0}_patcher'.format(p)).stop()


class V1TestCase(PatchedTestCase):
    """Base class for all helga_versionone tests
       helga_versionone.get_v1 is always patched to return self.v1 - a MagicMock()
       helga_versionone.settings is always patched to settings_stub
       helga_versionone.db is always patched
    """

    nick = 'me'
    channel = '#bots'

    db = patch('helga_versionone.db')
    settings = patch('helga_versionone.settings', settings_stub)
    get_v1 = patch('helga_versionone.get_v1')

    def setUp(self):
        # Starts the patches
        super(V1TestCase, self).setUp()

        self.v1 = MagicMock()
        # Depends on "get_v1" being in patches above
        self.get_v1.return_value = self.v1

        # client is mocked, but doesn't have to be patched.
        self.client = MagicMock()

    def assertAck(self):
        self.assertIn(self.client.msg.call_args[0][1], ACKS)

    def _test_command(self, cmd, expected=None, to_nick=False):
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
            target = self.nick if to_nick else self.channel

            def check(actual):
                self.client.msg.assert_called_once_with(target, expected)

            d.addCallback(check)
            return d
        else:
            self.assertEqual(d, expected)
