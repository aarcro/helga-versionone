from mock import patch

from .util import V1TestCase, writeable_settings_stub


class TestTakeCommand(V1TestCase):
    get_workitem = patch('helga_versionone.get_workitem')
    get_user = patch('helga_versionone.get_user')

    def test_in_owners(self):
        self.get_workitem().Owners = [self.nick, 'fhqwhgads']
        self.get_user.return_value = self.nick

        return self._test_command(
            'take whatever',
            'Dude {0}, you already own it!'.format(self.nick),
        )

    def test_not_in_owners_write_fail(self):
        self.get_workitem().Owners = ['fhqwhgads']
        self.get_user.return_value = self.nick

        return self._test_command(
            'take whatever',
            'I would, but I\'m not allowed to write :('
        )


class TestTakeCommandWithWrite(V1TestCase):
    settings = patch('helga_versionone.settings', writeable_settings_stub)
    get_workitem = patch('helga_versionone.get_workitem')
    get_user = patch('helga_versionone.get_user')

    def test_not_in_owners_write_ok(self):
        w = self.get_workitem()
        w.Owners = ['fhqwhgads']
        self.get_user.return_value = self.nick

        d = self._test_command(
            'take whatever',
        )

        def check(res):
            # Check data and commit called
            self.assertEquals(
                w.Owners,
                [self.nick],
            )
            self.v1.commit.assert_called_once_with()
            self.assertAck()

        d.addCallback(check)
        return d
