# coding=utf-8
from __future__ import division, absolute_import, print_function, unicode_literals
from urllib.parse import urljoin
import ssl
import logging
import requests
import websockets


class IRCCloudHTTPError(Exception):
    pass


class RateLimitedError(Exception):
    pass


class IRCCloudHTTPClient(object):
    def __init__(self, host, verify_certificate=True):
        # TODO: Test this SSL verification logic.
        self.log = logging.getLogger(__name__)
        self.host = host

        self.http = requests.Session()
        self.http.verify = verify_certificate
        self.ssl_context = ssl.create_default_context()
        if not verify_certificate:
            self.ssl_context.check_hostname = False
            self.ssl_context.verify_mode = ssl.CERT_NONE

        self.http.headers['User-Agent'] = 'IRCCloud-python'
        self.logged_in = False

    def get_url(self, path):
        return urljoin("https://%s" % self.host, path)

    def get_auth_formtoken(self):
        response = self.http.post(self.get_url("/chat/auth-formtoken"))
        response.raise_for_status()
        data = response.json()
        if not data['success']:
            raise IRCCloudHTTPError("Failure to get formtoken: %s" % data)
        return data['token']

    def login(self, email, password):
        token = self.get_auth_formtoken()
        request_data = {
            'token': token,
            'email': email,
            'password': password
        }
        headers = {'x-auth-formtoken': token}
        response = self.http.post(self.get_url("/chat/login"), data=request_data, headers=headers)
        if response.status_code == 400:
            data = response.json()
            if data['message'] == 'rate_limited':
                raise RateLimitedError(data)
        response.raise_for_status()
        data = response.json()
        if not data['success']:
            raise IRCCloudHTTPError("Failure to log in: %s" % data)
        self.log.info("Login successful, sid: %s", data['session'])
        self.logged_in = True

    def websocket(self):
        if not self.logged_in:
            raise IRCCloudHTTPError("Login required!")
        headers = {
            'Origin': self.get_url(''),
            'Cookie': 'session=%s' % (self.http.cookies['session'])
        }
        self.log.info("Connecting websocket...")
        return websockets.connect('wss://%s/' % self.host,
                                  extra_headers=headers,
                                  ssl=self.ssl_context)

    def fetch(self, path):
        url = self.get_url(path)
        response = self.http.get(url)
        response.raise_for_status()
        return response.text
