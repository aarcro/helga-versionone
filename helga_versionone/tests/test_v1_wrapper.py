from mock import patch, MagicMock
from unittest import TestCase
from httplib2 import HttpLib2ErrorWithResponse

from helga_versionone.v1_wrapper import property_required, HelgaOauthV1Server


class TestPropertyRequired(TestCase):
    def test_good_object_works(self):

        class A(object):
            foo = True

            @property_required('foo')
            def bar(self):
                return self.foo

        a = A()
        self.assertEqual(a.bar(), True)

    def test_lazy_object_works(self):

        class A(object):
            @property_required('foo')
            def bar(self):
                return self.foo

        a = A()
        a.foo = "I'm foo"
        self.assertEqual(a.bar(), "I'm foo")

    def test_broken_object_fails(self):

        class A(object):
            @property_required('foo')
            def bar(self):
                return "I don't really care about foo, but it is required"

        a = A()
        self.assertRaises(ValueError, a.bar)


class TestHelgaOauthV1Server(TestCase):
    def test_positional_args(self):
        s = HelgaOauthV1Server('example.com', 'instance_name')
        self.assertEquals(s.scheme, 'http')
        self.assertEquals(s.instance_url, 'http://example.com/instance_name/')

    def test_instance_url(self):
        s = HelgaOauthV1Server(instance_url='http://example.com/instance_name')
        self.assertEquals(s.scheme, 'http')
        self.assertEquals(s.address, 'example.com')
        self.assertEquals(s.instance, 'instance_name')

    def test_with_creds(self):
        creds = MagicMock()
        s = HelgaOauthV1Server(instance_url='http://example.com/instance_name', credentials=creds)
        creds.authorize.call_args.assert_called_once_with(s.httpclient)


class TestHelgaOauthV1ServerWithInstance(TestCase):
    def setUp(self):
        self.url = 'http://example.com/instance_name'
        self.server = HelgaOauthV1Server(instance_url=self.url)
        self.server.httpclient = MagicMock()
        self.server.httpclient.request.return_value = ('response', 'content')

    def test_fetch_get(self):
        e, c = self.server.fetch('/test')
        self.server.httpclient.request.call_args.assert_called_once_with(
            '{0}/test'.format(self.url), method='GET')
        self.assertEquals(e, None)
        self.assertEquals(c, 'content')

    def test_fetch_post(self):
        e, c = self.server.fetch('/test', postdata={'q': 'query'})
        self.server.httpclient.request.call_args.assert_called_once_with(
            '{0}/test'.format(self.url), method='POST', body='q=query')
        self.assertEquals(e, None)
        self.assertEquals(c, 'content')

    def test_fetch_get_fails(self):
        response = MagicMock()
        error = HttpLib2ErrorWithResponse('desc', response, 'error content')
        self.server.httpclient.request.side_effect = error
        e, c = self.server.fetch('/test')
        self.assertEqual(e, error)
        self.assertEqual(c, 'error content')
        self.assertEqual(e.response, response)
