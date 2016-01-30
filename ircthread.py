from collections import deque
import logging
from threading import Thread, Semaphore
import time

from oyoyo.client import IRCClient
from oyoyo.cmdhandler import DefaultCommandHandler
from oyoyo import helpers

import re

class IRCThreadCallbackHandler(DefaultCommandHandler):
    @classmethod
    def set_sms900(cls, sms900):
        cls.sms900 = sms900

    def __init__(self, client):
        super(IRCThreadCallbackHandler, self).__init__(client)
        self.cli = client

    def privmsg(self, _hostmask, _chan, _msg):
        logging.info("%s in %s said: %s" % (_hostmask, _chan, _msg))

        msg = _msg.decode("utf-8", "ignore")
        chan = _chan.decode("utf-8", "ignore")
        hostmask = _hostmask.decode("utf-8", "ignore")

        cmd_dispatch = {
            'stats': self.handle_cmd_stats,
            's':     self.handle_cmd_s,
            'a':     self.handle_cmd_a,
            'd':     self.handle_cmd_d,
            'h':     self.handle_cmd_h,
            'l':     self.handle_cmd_l
            }
        m = re.match('^\!(stats|s|a|d|h|l)( .*|$)', msg, re.UNICODE)
        if m:
            args = m.group(2)
            cmd_dispatch[m.group(1).strip()](hostmask, chan, args)

    def handle_cmd_stats(self, hostmask, chan, cmd):
        self._add_event('SHOW_STATS', {
            'hostmask' : hostmask
        })

    def handle_cmd_l(self, hostmask, chan, cmd):
        logging.info('s! %s %s %s' % (hostmask, chan, cmd))

        m = re.match('^\s*(\S+)$', cmd, re.UNICODE)
        if not m:
            helpers.msg(self.cli, chan, 'Usage: !l(ookup) <number>')
            return

        number = m.group(1)

        self._add_event('LOOKUP_NUMBER', {
            'hostmask' : hostmask,
            'number' : number
        })

    def handle_cmd_s(self, hostmask, chan, cmd):
        logging.info('s! %s %s %s' % (hostmask, chan, cmd))

        m = re.match('^\s*(\S+)\s+(.+)', cmd, re.UNICODE)
        if not m:
            helpers.msg(self.cli, chan, 'Usage: !s(end) <contact|number> <msg..>')
            return

        destination = m.group(1)
        msg = m.group(2)

        self._add_event('SEND_SMS', {
            'hostmask' : hostmask,
            'number' : destination,
            'msg' : msg
        })

    def handle_cmd_a(self, hostmask, chan, cmd):
        logging.info('s! %s %s %s' % (hostmask, chan, cmd))

        m = re.match('^\s*(\S+)\s+(\S+)\s*$', cmd, re.UNICODE)
        if not m:
            helpers.msg(self.cli, chan, 'Usage: !a(dd) contact number')
            return

        nickname = m.group(1)
        number = m.group(2)

        self._add_event('ADD_PB_ENTRY', {
            'hostmask' : hostmask,
            'nickname' : nickname,
            'number' : number
        })

    def handle_cmd_d(self, hostmask, chan, cmd):
        logging.info('s! %s %s %s' % (hostmask, chan, cmd))

        m = re.match('^\s*(\S+)\s*$', cmd, re.UNICODE)
        if not m:
            helpers.msg(self.cli, chan, 'Usage: !d(elete) contact')
            return
        nickname = m.group(1)

        self._add_event('DEL_PB_ENTRY', {
            'hostmask' : hostmask,
            'nickname' : nickname
        })


    def handle_cmd_h(self, hostmask, chan, cmd):
        helpers.msg(self.cli, chan, 'Commands: stats, s(end message), a(add contact), d(elete contact), l(ookup), h(elp)')

    def _add_event(self, event_type, data):
        event = {'event_src': 'IRC', 'event_type': event_type}
        event.update(data)
        self.sms900.add_event(event)

class IRCThread(Thread):
    def __init__(self, sms900, host, port, nick, channel):
        Thread.__init__(self)
        self.irc_host = host
        self.irc_port = port
        self.irc_nick = nick
        self.irc_channel = channel

        self.cmd_queue = deque()

        IRCThreadCallbackHandler.set_sms900(sms900)

    def run(self):
        while True:
            try:
                self.connect_and_run()
            except Exception as e:
                logging.info("Caught an exception, will try to reconnect!")
                self.cli = None

            logging.info("Sleeping for 5 seconds..")
            time.sleep(5)

    def connect_and_run(self):
        self.cli = IRCClient(IRCThreadCallbackHandler,
                             host=self.irc_host,
                             port=self.irc_port,
                             nick=self.irc_nick,
                             connect_cb=self.connect_callback)

        conn = self.cli.connect()
        while True:
            next(conn)
            while len(self.cmd_queue) > 0:
                cmd = self.cmd_queue.popleft()
                target = cmd[1]
                msg = cmd[2]
                logging.info('Handling event (%s) -> (%s, %s)' % (cmd, target, msg))
                helpers.msg(self.cli, target, msg)

            time.sleep(0.2)

    def connect_callback(self, cli):
        helpers.join(cli, self.irc_channel)

    def send_privmsg(self, target, msg):
        self.cmd_queue.append(['PRIVMSG', target, msg])
