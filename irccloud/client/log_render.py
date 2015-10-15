# coding=utf-8
from __future__ import division, absolute_import, print_function, unicode_literals
import logging
from datetime import datetime
from string import Template
from collections import defaultdict
from .messages import VERBATIM, MESSAGES, STATS


def eid_to_datetime(eid, tz=None):
    unixtime = eid // 1000000
    return datetime.fromtimestamp(unixtime, tz)


class TextLogRenderer(object):
    """Render IRCCloud log events to human-readable text."""
    def __init__(self, tz=None):
        self.log = logging.getLogger(__name__)
        self.tz = tz

    def render_buffer(self, lines):
        """ Take an iterable list of log events and yield human-readable text strings """
        for line in lines:
            try:
                yield self.render_line(line.body)
            except KeyError:
                self.log.exception("Rendering exception")

    def render_line(self, line):
        """ Render a single log event to a string. """
        time = eid_to_datetime(line['eid'], self.tz)
        msg = "[%s] " % (time.strftime('%Y-%m-%d %H:%M:%S'))
        if line['type'] == 'buffer_msg':
            msg += "<%s> %s" % (line.get('from', line.get('server')), line['msg'])
            return msg
        if line['type'] == 'buffer_me_msg':
            msg += "— %s %s" % (line['from'], line['msg'])
            return msg

        if line['type'] in ['joined_channel', 'you_joined_channel']:
            msg += '→ '
        elif line['type'] in ['parted_channel', 'you_parted_channel']:
            msg += '← '
        elif line['type'] == 'quit':
            msg += '⇐ '
        else:
            msg += '* '

        if line['type'] in VERBATIM:
            try:
                msg += line['msg']
            except KeyError:
                self.log.warn("Log type %s has no attribute 'msg'", line['type'])
        elif line['type'] in MESSAGES:
            temp = Template(MESSAGES[line['type']])
            msg += temp.safe_substitute(defaultdict(lambda: '', line))
        elif line['type'] in STATS:
            if 'parts' in line:
                msg += line['parts'] + ": "
            msg += line['msg']
        elif line['type'] == 'user_channel_mode':
            msg += '%s set %s %s' % (line.get('from', line.get('server')), line['diff'], line['nick'])
        elif line['type'] == 'channel_query':
            if line['query_type'] == 'timestamp':
                msg += 'channel timestamp is %s' % line['timestamp']
            elif line['query_type'] == 'mode':
                msg += 'channel mode is %s' % line['newmode']
            else:
                self.log.warn('Unknown channel_query type: %s', line['query_type'])
        elif line['type'] == 'channel_mode':
            msg += 'Channel mode set to %s by ' % line['diff']
            if 'from' in line:
                msg += line['from']
            else:
                msg += 'the server %s' % line['server']
        elif line['type'] == 'motd_response':
            msg += "\n".join(line['lines'])
        elif line['type'] in ['cap_ls', 'cap_req', 'cap_ack']:
            if line['type'] == 'cap_ls':
                msg += 'Available'
            if line['type'] == 'cap_req':
                msg += 'Requested'
            if line['type'] == 'cap_ack':
                msg += 'Acknowledged'
            msg += ' capabilities: %s' % ' | '.join(line['caps'])
        elif line['type'] == 'unknown_umode':
            if 'flag' in line:
                msg += line['flag'] + " "
            msg += line['msg']
        elif line['type'] == 'time':
            msg += 'Server time: %s' % line['time_string']
            if 'time_stamp' in line:
                msg += ' (%s)' % line['time_stamp']
            msg += ' - %s' % line['time_server']
        else:
            if 'msg' in line:
                msg += line['msg']
            self.log.warn('Unknown message type (%s)', line['type'])
        return msg
