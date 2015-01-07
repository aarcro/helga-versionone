from mock import patch
from pretend import stub

from .util import V1TestCase, writeable_settings_stub

# Tests for both tests and tasks as they are the same code path


def make_thing(name, num, status_name, status_order):
    return stub(
        Name='{0}-{1}'.format(name, num),
        url='http://example.com/{0}'.format(num),
        Status=stub(
            Name=status_name,
            Order=status_order,
        )
    )


class TestThingCommand(V1TestCase):
    get_workitem = patch('helga_versionone.get_workitem')

    def setUp(self):
        super(TestThingCommand, self).setUp()
        self.results = [
            make_thing('thing', 1, 'Done', 99),
            make_thing('thing', 2, 'None', 0),
            make_thing('thing', 3, 'In Progress', 50),
        ]
        self.results_ordered = [self.results[i] for i in [1, 2, 0]]
        self.v1.Task.where().select.return_value = self.results

    def test_list_tasks(self):
        return self._test_command(
            'tasks whatever',
            '\n'.join([
                '[{0}] {1} {2}'.format(t.Status.Name, t.Name, t.url)
                for t in self.results_ordered
            ]),
        )

    def test_list_tests_none(self):
        return self._test_command(
            'tests whatever',
            'Didn\'t find any Tests for whatever',
        )

    def test_bad_action(self):
        return self._test_command(
            'tests whatever fhqwhgads',
            'I can\'t just "fhqwhgads" that, {0}'.format(self.nick),
        )

    def test_add_failed_for_title(self):
        return self._test_command(
            'tests whatever add',
            'I\'m going to need a title for that, {0}'.format(self.nick),
        )

    def test_add_failed_no_write(self):
        return self._test_command(
            'tasks whatever add Do a little dance',
            'I\'m sorry {0}, write access is disabled'.format(self.nick),
        )


class TestThingCommandWithWrite(V1TestCase):
    settings = patch('helga_versionone.settings', writeable_settings_stub)
    get_workitem = patch('helga_versionone.get_workitem')

    def test_tests_add_ok(self):
        self.get_workitem().idref = 3
        name = 'Do a little dance'
        url = 'http://example.com'

        self.v1.Test.create.return_value = stub(
            Name=name,
            url=url,
        )

        d = self._test_command(
            'tests whatever add {0}'.format(name),
            'I created {0} {1} for you, {2}'.format(name, url, self.nick)
        )

        def check(res):
            # Check data and commit called
            self.v1.Test.create.assert_called_once_with(
                Name=name,
                Parent=3,
            )

        d.addCallback(check)
        return d
