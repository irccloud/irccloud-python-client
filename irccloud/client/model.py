# coding=utf-8
from __future__ import division, absolute_import, print_function, unicode_literals
from collections import deque, namedtuple


class Connection(object):
    def __init__(self, id):
        self.id = id
        self.port = None
        self.hostname = None
        self.buffers = []
    def __repr__(self):
        return "<Connection id: %s, hostname: %s>" % (self.id, self.hostname)


class Buffer(object):
    def __init__(self, id, name, buffer_type, connection, max_backlog=500):
        self.id = id
        self.name = name
        self.buffer_type = buffer_type
        self.connection = connection
        self.lines = deque(maxlen=max_backlog)
        self.archived = False
        self.members = []

    def remove_member(self, nick):
        for member in self.members:
            if member.nick == nick:
                self.members.remove(member)
                return

    def __repr__(self):
        return "<Buffer id: %s, name: %s>" % (self.id, self.name)

User = namedtuple('User', 'nick realname usermask')
