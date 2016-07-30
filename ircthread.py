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

    @classmethod
    def set_pong_queue(cls, pong_queue):
        cls.pong_queue = pong_queue

    @classmethod
    def set_channel(cls, channel):
        cls.channel = channel

    def __init__(self, client):
        super(IRCThreadCallbackHandler, self).__init__(client)
        self.cli = client

    def ping(self, prefix, server):
        logging.info("PING/%s/%s" % (prefix, server))
        self.client.send("PONG", server)

    def pong(self, prefix, server, something):
        logging.info("PONG/%s/%s/%s" % (prefix, server, something))
        self.pong_queue.append(server)

    def nicknameinuse(self, server, b, nickname, msg):
        logging.info("Nickname already in use: %s/%s/%s/%s" % (server, b, nickname, msg))
        # FIXME: This algorithm is stupid
        nickname = nickname.decode('ascii') + "_"
        logging.info("Trying with %s.." % nickname)
        self.client.send("NICK %s" % nickname)

    def welcome(self, a, b, c):
        logging.info("(001) Welcome: %s/%s/%s" % (a, b, c))
        self.client.send("JOIN %s" % self.channel)

    def privmsg(self, _hostmask, _chan, _msg):
        logging.info("%s in %s said: %s" % (_hostmask, _chan, _msg))

        msg = _msg.decode("utf-8", "ignore")
        chan = _chan.decode("utf-8", "ignore")
        hostmask = _hostmask.decode("utf-8", "ignore")

        cmd_dispatch = {
            's':     self._parse_cmd_send_sms,
            'a':     self._parse_cmd_pb_add,
            'd':     self._parse_cmd_pb_del,
            'h':     self._parse_cmd_help,
            'l':     self._parse_cmd_lookup_carrier
            }
        m = re.match('^\!(s|a|d|h|l)( .*|$)', msg, re.UNICODE)
        if m:
            args = m.group(2)
            cmd_dispatch[m.group(1).strip()](hostmask, chan, args)

    def _parse_cmd_send_sms(self, hostmask, chan, cmd):
        logging.info('s! %s %s %s' % (hostmask, chan, cmd))

        m = re.match('^\s*(\S+)\s+(.+)', cmd, re.UNICODE)
        if not m:
            helpers.msg(self.cli, chan, 'Usage: !s(end) <contact|number> <msg..>')
            return

        destination = m.group(1)
        msg = m.group(2)

        self.sms900.queue_event('SEND_SMS', {
            'hostmask' : hostmask,
            'number' : destination,
            'msg' : msg
        })

    def _parse_cmd_pb_add(self, hostmask, chan, cmd):
        logging.info('s! %s %s %s' % (hostmask, chan, cmd))

        m = re.match('^\s*(\S+)\s+(\S+)\s*$', cmd, re.UNICODE)
        if not m:
            helpers.msg(self.cli, chan, 'Usage: !a(dd) contact number')
            return

        nickname = m.group(1)
        number = m.group(2)

        self.sms900.queue_event('ADD_PB_ENTRY', {
            'hostmask' : hostmask,
            'nickname' : nickname,
            'number' : number
        })

    def _parse_cmd_pb_del(self, hostmask, chan, cmd):
        logging.info('s! %s %s %s' % (hostmask, chan, cmd))

        m = re.match('^\s*(\S+)\s*$', cmd, re.UNICODE)
        if not m:
            helpers.msg(self.cli, chan, 'Usage: !d(elete) contact')
            return
        nickname = m.group(1)

        self.sms900.queue_event('DEL_PB_ENTRY', {
            'hostmask' : hostmask,
            'nickname' : nickname
        })

    def _parse_cmd_lookup_carrier(self, hostmask, chan, cmd):
        logging.info('s! %s %s %s' % (hostmask, chan, cmd))

        m = re.match('^\s*(\S+)$', cmd, re.UNICODE)
        if not m:
            helpers.msg(self.cli, chan, 'Usage: !l(ookup) <number>')
            return

        number = m.group(1)

        self.sms900.queue_event('LOOKUP_CARRIER', {
            'hostmask' : hostmask,
            'number' : number
        })

    def _parse_cmd_help(self, hostmask, chan, cmd):
        helpers.msg(self.cli, chan, 'Commands: s(end message), a(add contact), d(elete contact), l(ookup), h(elp)')

class IRCThread(Thread):
    PING_INTERVAL = 60
    PING_TIMEOUT = 180

    def __init__(self, sms900, host, port, nick, channel):
        Thread.__init__(self)
        self.irc_host = host
        self.irc_port = port
        self.irc_nick = nick

        self.pong_queue = deque()
        self.cmd_queue = deque()

        IRCThreadCallbackHandler.set_sms900(sms900)
        IRCThreadCallbackHandler.set_pong_queue(self.pong_queue)
        IRCThreadCallbackHandler.set_channel(channel)

    def run(self):
        while True:
            try:
                self._connect_and_run()
            except Exception as e:
                logging.info("Exception caught, reconnecting: %s" % e)

            logging.info("Sleeping for 5 seconds..")
            time.sleep(5)

    def _connect_and_run(self):
        cli = IRCClient(IRCThreadCallbackHandler,
                        host=self.irc_host,
                        port=self.irc_port,
                        nick=self.irc_nick)

        self.ping_last_reply = time.time()
        self.ping_sent_at = False
        self.pong_queue.clear()

        conn = cli.connect()
        while True:
            next(conn)
            while len(self.cmd_queue) > 0:
                cmd = self.cmd_queue.popleft()
                target = cmd[1]
                msg = cmd[2]
                logging.info('Handling event (%s) -> (%s, %s)' % (cmd, target, msg))
                helpers.msg(cli, target, msg)

            self._check_connection(cli)

            time.sleep(0.2)

    def _check_connection(self, cli):
        if not self.ping_sent_at:
            if time.time() - self.ping_last_reply > self.PING_INTERVAL:
                self.ping_sent_at = time.time()
                cli.send("PING %s" % int(self.ping_sent_at))
        else:
            lag = time.time() - self.ping_sent_at

            # We'll just assume that any pong received is good enough
            if len(self.pong_queue) > 0:
                logging.info("Current lag: %s" % lag)

                self.ping_sent_at = None
                self.ping_last_reply = time.time()
                self.pong_queue.clear()
            else:
                if lag > self.PING_TIMEOUT:
                    raise Exception("Lag is %s, exceeded timeout %s" % (lag, self.PING_TIMEOUT))

    def send_privmsg(self, target, msg):
        self.cmd_queue.append(['PRIVMSG', target, msg])
