# coding=utf-8
from __future__ import division, absolute_import, print_function, unicode_literals
import asyncio
import logging
import json
from .messages import BUFFER_MESSAGES
from .http_client import IRCCloudHTTPClient
from .log_render import TextLogRenderer
from .model import Connection, Buffer, User


IGNORE_MESSAGES = {'idle', 'backlog_starts', 'end_of_backlog', 'backlog_complete', 'num_invites',
                   'heartbeat_echo', 'isupport_params', 'whois_response'}
CREATION_MESSAGES = {'makeserver', 'makebuffer', 'channel_init'}


class IRCCloudClient(object):
    """ A Python client for IRCCloud, which connects using websockets. """
    def __init__(self, host="www.irccloud.com"):
        self.log = logging.getLogger(__name__)
        self.irccloud = IRCCloudHTTPClient(host)
        self.stream_id = None
        self.user_info = None
        self.connections = {}
        self.buffers = {}
        self.log_renderer = TextLogRenderer()

    def login(self, email, password):
        self.irccloud.login(email, password)

    def oob_fetch(self, url):
        self.log.info("Starting OOB fetch...")
        oob = self.irccloud.fetch(url)
        for message in oob:
            self.handle_message(message, oob=True)
        self.log.info("OOB processing completed. %s connections, %s buffers.",
                      len(self.connections), len(self.buffers))

    def handle_message(self, message, oob=False):
        mtype = message['type']
        if mtype == 'header':
            self.stream_id = message['streamid']
        elif mtype == 'stat_user':
            self.user_info = message
        elif mtype == 'oob_include':
            self.oob_fetch(message['url'])
        elif mtype in IGNORE_MESSAGES:
            pass
        elif mtype in CREATION_MESSAGES:
            self.handle_creation_message(mtype, message)
        elif mtype in BUFFER_MESSAGES:
            self.handle_buffer_message(message['bid'], message, oob)
        else:
            self.log.warn("Unhandled message. Type: %s, message: %s", mtype, message)

    def handle_creation_message(self, mtype, message):
        if mtype == 'makeserver':
            conn = Connection(message['cid'])
            conn.hostname = message['ircserver']
            conn.port = message['port']
            self.connections[message['cid']] = conn
        elif mtype == 'makebuffer':
            conn = self.connections[message['cid']]
            buff = Buffer(message['bid'], message['name'], message['type'], conn)
            conn.buffers.append(buff)
            self.buffers[message['bid']] = buff
        elif mtype == 'channel_init':
            buff = self.buffers[message['bid']]
            for member in message['members']:
                buff.members.append(User(member['nick'], member['realname'], member['usermask']))

    def handle_buffer_message(self, bid, message, oob):
        buff = self.buffers[bid]
        if message['type'] in ('quit', 'part'):
            buff.remove_member(message['nick'])
        if message['type'] == 'join':
            buff.members.append(User(message['nick'], message['realname'], message['usermask']))

        if not oob:
            print(self.log_renderer.render_line(message))

    @asyncio.coroutine
    def run(self):
        socket = yield from self.irccloud.websocket()
        while True:
            res = yield from socket.recv()
            if res is None:
                break
            self.handle_message(json.loads(res))
        yield from socket.close()
