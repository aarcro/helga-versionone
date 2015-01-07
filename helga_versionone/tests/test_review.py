from mock import patch

from .util import V1TestCase, writeable_settings_stub, settings_stub


class ReviewMixin(object):
    def setUp(self):
        super(ReviewMixin, self).setUp()
        self.cr_field = settings_stub.VERSIONONE_CR_FIELDS[0]
        self.link = 'http://example.com/code_review'
        self.new_link = 'http://another.link.com/'
        setattr(self.get_workitem(), self.cr_field, self.link)


class TestReviewCommand(ReviewMixin, V1TestCase):
    get_workitem = patch('helga_versionone.get_workitem')

    def test_problem(self):
        # Field names are wrong in settings, or looking for an object that
        # doesn't Actually support reviews
        w = self.get_workitem()
        for field in settings_stub.VERSIONONE_CR_FIELDS:
            delattr(w, field)

        return self._test_command(
            'cr whatever',
            'I\'m sorry {0}, item "whatever" doesn\'t support reviews'.format(self.nick),
        )

    def test_results(self):
        return self._test_command(
            'cr whatever',
            'whatever Reviews: {0}'.format(self.link),
        )

    def test_set_append_fail(self):
        return self._test_command(
            'review whatever {0}'.format(self.new_link),
            'I would, but I\'m not allowed to write :('
        )


class TestReviewCommandWithWrite(ReviewMixin, V1TestCase):
    settings = patch('helga_versionone.settings', writeable_settings_stub)
    get_workitem = patch('helga_versionone.get_workitem')

    def test_set_append(self):
        w = self.get_workitem()
        d = self._test_command(
            'cr whatever {0}'.format(self.new_link),
        )

        def check(res):
            # Check v1 attr, and commit called
            self.assertEquals(
                # self.v1.[w].[cr_field]
                getattr(w, self.cr_field),
                ' '.join([self.link, self.new_link]),
            )
            self.v1.commit.assert_called_once_with()
            self.assertAck()

        d.addCallback(check)
        return d

    def test_set_replace(self):
        w = self.get_workitem()
        d = self._test_command(
            'cr whatever !{0}'.format(self.new_link),
        )

        def check(res):
            # Check v1 attr, and commit called
            self.assertEquals(
                # self.v1.[w].[cr_field]
                getattr(w, self.cr_field),
                self.new_link,
            )
            self.v1.commit.assert_called_once_with()
            self.assertAck()

        d.addCallback(check)
        return d

    def test_set_ignored(self):
        return self._test_command(
            'cr whatever {0}'.format(self.link),
            'Already got that one {0}'.format(self.nick),
        )
