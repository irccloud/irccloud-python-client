# coding=utf-8
from __future__ import division, absolute_import, print_function, unicode_literals
import asyncio
import logging
import ujson as json
from .messages import BUFFER_MESSAGES
from .http_client import IRCCloudHTTPClient
from .model import Connection, Buffer, User


IGNORE_MESSAGES = {'idle', 'backlog_starts', 'end_of_backlog', 'backlog_complete', 'num_invites',
                   'heartbeat_echo', 'isupport_params', 'whois_response', 'user_account'}
CREATION_MESSAGES = {'makeserver', 'makebuffer', 'channel_init'}
SERVER_MESSAGES = {'server_details_changed', 'status_changed'}


class IRCCloudClient(object):
    """ A Python client for IRCCloud, which connects using websockets. """
    def __init__(self, host="www.irccloud.com", verify_certificate=True,
                 track_channel_state=True):
        self.log = logging.getLogger(__name__)
        self.irccloud = IRCCloudHTTPClient(host, verify_certificate=verify_certificate)
        self.track_channel_state = track_channel_state
        self.stream_id = None
        self.user_info = None
        self.connections = {}
        self.buffers = {}
        self.message_callback = None
        self.state_callback = None
        self.running = True
        self.reqid = 0
        self.response_queues = {}

    def login(self, email, password):
        self.irccloud.login(email, password)

    @asyncio.coroutine
    def add_server(self, name, hostname, port, nickname, realname, ssl=False,
                   server_pass=None, nspass=None, joincommands=None, channels=None):
        if ssl is True:
            ssl = "1"
        else:
            ssl = "0"

        message = {'_method': 'add-server',
                   'hostname': hostname, 'port': port, 'nickname': nickname,
                   'realname': realname, 'server_pass': server_pass, 'ssl': ssl,
                   'nspass': nspass, 'joincommands': joincommands, 'channels': channels}
        response = yield from self.send_message(message)
        if response['success'] is False:
            raise Exception("Error creating network: %s" % response['message'])
        return response

    @asyncio.coroutine
    def join_channel(self, conn, channel, key=None):
        message = {'_method': 'join',
                   'cid': conn.id, 'channel': channel}
        if key is not None:
            message['key'] = key
        response = yield from self.send_message(message)
        if response['success'] is False:
            raise Exception("Error creating network: %s" % response['message'])
        return response

    @asyncio.coroutine
    def say(self, to_buffer, message):
        # TODO: allow sending messages to buffers which aren't open yet (per docs)
        message = {'_method': 'say',
                   'cid': to_buffer.connection.id,
                   'to': to_buffer.name, 'msg': message}
        response = yield from self.send_message(message)
        if response['success'] is False:
            raise Exception("Error sending message: %s" % response['message'])
        return response

    @asyncio.coroutine
    def send_message(self, message):
        self.reqid += 1
        reqid = self.reqid
        message['_reqid'] = reqid

        res_queue = asyncio.Queue(1)
        self.response_queues[reqid] = res_queue
        yield from self.socket.send(json.dumps(message))
        response = yield from res_queue.get()
        del self.response_queues[reqid]
        return response

    @asyncio.coroutine
    def oob_fetch(self, url):
        self.log.info("Starting OOB fetch...")
        if self.state_callback:
            self.state_callback('backlog_fetch')

        oob_data = self.irccloud.fetch(url)
        self.log.info("Parsing OOB data")
        for message in json.loads(oob_data):
            yield from self.handle_message(message, oob=True)
        self.log.info("OOB processing completed. %s connections, %s buffers.",
                      len(self.connections), len(self.buffers))
        if self.state_callback:
            self.state_callback('online')

    @asyncio.coroutine
    def handle_message(self, message, oob=False):
        if '_reqid' in message and message['_reqid'] in self.response_queues:
            yield from self.response_queues[message['_reqid']].put(message)
            if message['success'] is False:
                return

        try:
            mtype = message['type']
        except KeyError:
            self.log.error("No message type in message: %s", message)
            return

        if mtype == 'header':
            self.stream_id = message['streamid']
        elif mtype == 'stat_user':
            self.user_info = message
        elif mtype == 'oob_include':
            yield from self.oob_fetch(message['url'])
        elif mtype in IGNORE_MESSAGES:
            pass
        elif mtype in CREATION_MESSAGES:
            self.handle_creation_message(mtype, message)
        elif mtype in SERVER_MESSAGES:
            self.handle_server_message(mtype, message)
        elif mtype in BUFFER_MESSAGES:
            self.handle_buffer_message(message['bid'], message, oob)
        else:
            self.log.warn("Unhandled message. Type: %s, message: %s", mtype, message)

    def handle_creation_message(self, mtype, message):
        if mtype == 'makeserver':
            conn = Connection(message['cid'])
            conn.hostname = message['ircserver']
            conn.port = message['port']
            conn.status = message.get('status')
            self.connections[message['cid']] = conn
        elif mtype == 'makebuffer':
            conn = self.connections[message['cid']]
            buff = Buffer(message['bid'], message['name'], message['type'], conn)
            buff.archived = message.get('archived', False)
            conn.buffers.append(buff)
            self.buffers[message['bid']] = buff
        elif mtype == 'channel_init':
            buff = self.buffers[message['bid']]
            if self.track_channel_state:
                for member in message['members']:
                    buff.members.append(User(member['nick'], member['realname'], member['usermask']))

    def handle_server_message(self, mtype, message):
        conn = self.connections[message['cid']]
        if mtype == 'status_changed':
            conn.status = message['new_status']
        elif mtype == 'server_details_changed':
            conn.status = message['status']

    def handle_buffer_message(self, bid, message, oob):
        buff = self.buffers[bid]
        if self.track_channel_state:
            if message['type'] in ('quit', 'part'):
                buff.remove_member(message['nick'])
            if message['type'] == 'join':
                buff.members.append(User(message['nick'], message['realname'], message['usermask']))

        if not oob and self.message_callback is not None:
            self.message_callback(buff, message)

    def register_message_callback(self, callback):
        self.message_callback = callback

    def register_state_callback(self, callback):
        self.state_callback = callback

    def disconnect(self):
        self.running = False

    @asyncio.coroutine
    def run(self):
        if self.state_callback:
            self.state_callback('connecting')

        self.socket = yield from self.irccloud.websocket()
        if self.state_callback:
            self.state_callback('connected')

        while self.running:
            res = yield from self.socket.recv()
            if res is None:
                break
            yield from self.handle_message(json.loads(res))
        yield from self.socket.close()
        if self.state_callback:
            self.state_callback('disconnected')
