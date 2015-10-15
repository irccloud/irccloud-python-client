# coding=utf-8
from __future__ import division, absolute_import, print_function, unicode_literals
from collections import deque, namedtuple


class Connection(object):
    def __init__(self, id):
        self.id = id
        self.port = None
        self.hostname = None
        self.buffers = []


class Buffer(object):
    def __init__(self, id, name, buffer_type, connection, max_backlog=500):
        self.id = id
        self.buffer_type = buffer_type
        self.connection = connection
        self.lines = deque(maxlen=max_backlog)
        self.members = []

    def remove_member(self, nick):
        for member in self.members:
            if member.nick == nick:
                self.members.remove(member)
                return

User = namedtuple('User', 'nick realname usermask')
