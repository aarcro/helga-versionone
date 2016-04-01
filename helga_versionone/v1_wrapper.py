"""Patch v1pysdk to use non-file credential stores"""

import logging
import httplib2
import urllib2

from urllib import urlencode
from urllib2 import HTTPBasicAuthHandler, HTTPCookieProcessor

from expiringdict import ExpiringDict
from functools import wraps
from urlparse import urlparse
from v1pysdk.client import V1Server
from v1pysdk.v1meta import V1Meta

try:
    from xml.etree import ElementTree
except ImportError:  # pragma: no cover
    from elementtree import ElementTree


logger = logging.getLogger(__name__)


class property_required(object):
    """Decorate a method to require certian properties be populated"""

    def __init__(self, *args):
        """Arguments to the decorator are proprties which must be non-None"""
        self.props = args

    def __call__(self, fn):
        """Called once durring decoration, returns the real func to be called"""

        @wraps(fn)
        def wrapped_fn(herself, *args, **kwargs):
            for prop in self.props:
                if getattr(herself, prop, None) is None:
                    msg = 'Required property {0} is missing from {1}'.format(prop, herself)
                    logger.error(msg)
                    raise ValueError(msg)
            return fn(herself, *args, **kwargs)

        return wrapped_fn


class HelgaV1Meta(V1Meta):  # pragma: no cover
    def __init__(self, *args, **kw):
        # Coppied from V1Meta, but use our own Server class
        self.server = HelgaOauthV1Server(*args, **kw)
        # ...And a cache that expires
        self.global_cache = ExpiringDict(max_len=100, max_age_seconds=10)
        self.dirtylist = []

    def asset_class(self, asset_type_name):
        Klass = super(HelgaV1Meta, self).asset_class(asset_type_name)
        # Always use the current V1Meta instance, not the closed in one
        Klass._v1_v1meta = self
        return Klass


class HelgaOauthV1Server(V1Server):
    "Accesses a V1 HTTP server as a client of the XML API protocol"
    API_PATH = "/rest-1.oauth.v1"

    def __init__(self, address="localhost", instance="VersionOne.Web", password='',
                 scheme="http", instance_url=None, credentials=None, use_password_as_token=False):
        # How hacky is this?
        self.logger = logging.getLogger(__name__ + '.v1_client')
        self.logger.setLevel(logging.INFO)
        # Do not make super call, base implementation requires username/password
        if instance_url:
            self.instance_url = instance_url
            parsed = urlparse(instance_url)
            self.address = parsed.netloc
            self.instance = parsed.path.strip('/')
            self.scheme = parsed.scheme
        else:
            self.address = address
            self.instance = instance.strip('/')
            self.scheme = scheme
            self.instance_url = self.build_url('')

        self.httpclient = None

        if credentials is not None:
            self.set_credentials(credentials)

        # Cheating to support tokens, since I know the internals
        if use_password_as_token:
            self.username = ''
            self.password = password
            self.use_password_as_token = use_password_as_token
            self._install_opener()
            # Become the parent class (for opener style get/post methods
            self.__class__ = V1Server

    def _install_opener(self):
        base_url = self.build_url('')
        password_manager = urllib2.HTTPPasswordMgrWithDefaultRealm()
        password_manager.add_password(None, base_url, self.username, self.password)
        # only use the first Auth_handler to avoid the busted NTLM handler
        self.opener = urllib2.build_opener(HTTPBasicAuthHandler(password_manager))
        if self.use_password_as_token:
            self.opener.addheaders.append(('Authorization', 'Bearer ' + self.password))
        self.opener.add_handler(HTTPCookieProcessor())
        # No attempt is made to clear the cache when the creds change.
        # We assume all users have the same read-access.

    def set_credentials(self, creds):
        # If there are memory leaks, they might come from here
        self.httpclient = httplib2.Http()
        creds.authorize(self.httpclient)

    @property_required('httpclient')
    def http_get(self, url):
        return self.httpclient.request(url, method='GET')  # pragma: no cover

    @property_required('httpclient')
    def http_post(self, url, data=''):
        return self.httpclient.request(url, method='POST', body=data)  # pragma: no cover

    def fetch(self, path, query='', postdata=None):
        "Perform an HTTP GET or POST depending on whether postdata is present"
        url = self.build_url(path, query=query)
        try:
            if postdata is not None:
                if isinstance(postdata, dict):
                    postdata = urlencode(postdata)
                response, body = self.http_post(url, postdata)
            else:
                response, body = self.http_get(url)
            return (None, body)
        except httplib2.HttpLib2ErrorWithResponse, e:
            if e.response.status == 401:
                raise  # pragma: no cover
            body = e.content
            return (e, body)

    def get_asset_xml(self, asset_type_name, oid):
        path = self.API_PATH + '/Data/{0}/{1}'.format(asset_type_name, oid)
        return self.get_xml(path)

    def get_query_xml(self, asset_type_name, where=None, sel=None):
        path = self.API_PATH + '/Data/{0}'.format(asset_type_name)
        query = {}
        if where is not None:
                query['Where'] = where
        if sel is not None:
                query['sel'] = sel
        return self.get_xml(path, query=query)

    def execute_operation(self, asset_type_name, oid, opname):
        path = self.API_PATH + '/Data/{0}/{1}'.format(asset_type_name, oid)
        query = {'op': opname}
        return self.get_xml(path, query=query, postdata={})

    def get_attr(self, asset_type_name, oid, attrname):
        path = self.API_PATH + '/Data/{0}/{1}/{2}'.format(asset_type_name, oid, attrname)
        return self.get_xml(path)

    def create_asset(self, asset_type_name, xmldata, context_oid=''):
        body = ElementTree.tostring(xmldata, encoding="utf-8")
        query = {}
        if context_oid:
            query = {'ctx': context_oid}
        path = self.API_PATH + '/Data/{0}'.format(asset_type_name)
        return self.get_xml(path, query=query, postdata=body)

    def update_asset(self, asset_type_name, oid, update_doc):
        newdata = ElementTree.tostring(update_doc, encoding='utf-8')
        path = self.API_PATH + '/Data/{0}/{1}'.format(asset_type_name, oid)
        return self.get_xml(path, postdata=newdata)
