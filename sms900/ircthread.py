import logging
import re
import threading
import time
from collections import deque
from datetime import timedelta
from threading import Thread

from irc.bot import ExponentialBackoff, SingleServerIRCBot

MSG_SEND_INTERVAL = timedelta(milliseconds=500)
KEEPALIVE_INTERVAL = 60
ACTIVITY_TIMEOUT = 180
MAX_SEND_ATTEMPTS = 3


class IRCBot(SingleServerIRCBot):
    def __init__(self, sms900, host, port, nick, channel):
        SingleServerIRCBot.__init__(self,
                                    [(host, port)],
                                    nick,
                                    nick,
                                    recon=ExponentialBackoff(min_interval=5, max_interval=60))
        self.sms900 = sms900
        self.channel = channel
        self.cmd_queue = deque()
        self._setup_done = False
        self._lock = threading.Lock()
        self.last_activity = time.monotonic()
        self.reactor.add_global_handler("all_events", self._touch)

    def _touch(self, connection, event):
        self.last_activity = time.monotonic()

    def on_welcome(self, connection, event):
        logging.info("Connected, joining %s", self.channel)
        connection.join(self.channel)
        # The reactor and scheduler outlive connections, so schedule exactly once
        with self._lock:
            if not self._setup_done:
                connection.reactor.scheduler.execute_every(KEEPALIVE_INTERVAL, self._keepalive)
                connection.reactor.scheduler.execute_every(MSG_SEND_INTERVAL, self._drain_cmd_queue)
                self._setup_done = True

    def _keepalive(self):
        # set_keepalive() schedules an unguarded ping that raises into the
        # reactor loop while disconnected, killing it; ping manually instead
        if self.connection.is_connected():
            self.connection.ping('keep-alive')

    def on_nicknameinuse(self, connection, event):
        new_nick = connection.get_nickname() + "_"
        logging.info("Nickname in use, trying %s", new_nick)
        connection.nick(new_nick)

    def on_pubmsg(self, connection, event):
        self._handle_message(connection, event, event.target)

    def on_privmsg(self, connection, event):
        self._handle_message(connection, event, event.source.nick)

    def _handle_message(self, connection, event, chan):
        hostmask = f"{event.source.nick}!{event.source.user}@{event.source.host}"
        msg = event.arguments[0]

        logging.info("%s in %s said: %s", hostmask, chan, msg)

        self.sms900.on_privmsg_received(hostmask, chan, msg)

        cmd_dispatch = {
            's':     self._parse_cmd_send_sms,
            'S':     self._parse_cmd_send_sms_to_skatteola,
            'a':     self._parse_cmd_pb_add,
            'd':     self._parse_cmd_pb_del,
            'h':     self._parse_cmd_help,
            'l':     self._parse_cmd_lookup_carrier,
            'r':     self._parse_cmd_reindex,
            'op':    self._parse_cmd_openai_prompt,
            'or':    self._parse_cmd_openai_reset_history,
            'oc':    self._parse_cmd_openai_comment_on_context,
            'om':    self._parse_cmd_openai_model,
            'oi':    self._parse_cmd_openai_info,
            'od':    self._parse_cmd_openai_default,
            'tc':    self._parse_cmd_timers_clear,
            'tl':    self._parse_cmd_timers_list,
            }
        m = re.match('^!(s|S|a|d|h|l|r|op|or|oc|om|oi|od|tc|tl)( .*|$)', msg, re.UNICODE)
        if m:
            args = m.group(2)
            cmd_dispatch[m.group(1).strip()](hostmask, chan, args)

    def _reply(self, target, msg):
        self.connection.privmsg(target, msg)

    def _drain_cmd_queue(self):
        if self.connection.is_connected():
            lag = time.monotonic() - self.last_activity
            if lag > ACTIVITY_TIMEOUT:
                logging.warning("No activity from server for %.0f seconds, forcing reconnect" % lag)
                self.last_activity = time.monotonic()
                self.connection.disconnect("Ping timeout")
                return
        else:
            logging.debug("Not connected, deferring %s queued message(s)" % len(self.cmd_queue))
            return

        with self._lock:
            if not self.cmd_queue:
                return
        target, msg, attempts = self.cmd_queue.popleft()
        logging.info('Handling event (%s, %s)' % (target, msg))
        try:
            self.connection.privmsg(target, msg)
        except Exception as e:
            attempts += 1
            if attempts < MAX_SEND_ATTEMPTS:
                logging.warning("Failed to send privmsg to %s (attempt %s): %s" % (target, attempts, e))
                self.cmd_queue.appendleft((target, msg, attempts))
            else:
                logging.error("Dropping privmsg to %s after %s attempts: %s" % (target, attempts, msg))

    def send_privmsg(self, target, msg):
        for line in msg.split('\n'):
            line = line.strip()
            if line:  # Skip empty lines
                self.cmd_queue.append((target, line, 0))

    def _parse_cmd_send_sms_to_skatteola(self, hostmask, chan, cmd):
        return self._parse_cmd_send_sms(hostmask, chan, "skatteola %s" % cmd)

    def _parse_cmd_send_sms(self, hostmask, chan, cmd):
        logging.info('s! %s %s', hostmask, cmd)

        m = re.match(r'^\s*(\S+)\s+(.+)', cmd, re.UNICODE)
        if not m:
            self._reply(chan, 'Usage: !s(end) <contact|number> <msg..>')
            return

        destination = m.group(1)
        msg = m.group(2)

        self.sms900.queue_event('SEND_SMS', {
            'hostmask' : hostmask,
            'number' : destination,
            'msg' : msg
        })

    def _parse_cmd_pb_add(self, hostmask, chan, cmd):
        logging.info('a! %s %s', hostmask, cmd)

        m = re.match(r'^\s*(\S+)\s+(\S+)\s*$', cmd, re.UNICODE)
        if not m:
            self._reply(chan, 'Usage: !a(dd) contact <number|email>')
            return

        nickname = m.group(1)

        email = None
        number = None

        if '@' in m.group(2):
            email = m.group(2)
        else:
            number = m.group(2)

        self.sms900.queue_event('ADD_PB_ENTRY', {
            'hostmask' : hostmask,
            'nickname' : nickname,
            'email' : email,
            'number' : number
        })

    def _parse_cmd_pb_del(self, hostmask, chan, cmd):
        logging.info('d! %s %s', hostmask, cmd)

        m = re.match(r'^\s*(\S+)\s*$', cmd, re.UNICODE)
        if not m:
            self._reply(chan, 'Usage: !d(elete) contact [email]')
            return

        nickname = None
        email = None

        if '@' in m.group(1):
            email = m.group(1)
        else:
            nickname = m.group(1)

        self.sms900.queue_event('DEL_PB_ENTRY', {
            'hostmask' : hostmask,
            'nickname' : nickname,
            'email' : email
        })

    def _parse_cmd_lookup_carrier(self, hostmask, chan, cmd):
        logging.info('s! %s %s', hostmask, cmd)

        m = re.match(r'^\s*(\S+)$', cmd, re.UNICODE)
        if not m:
            self._reply(chan, 'Usage: !l(ookup) <number>')
            return

        number = m.group(1)

        self.sms900.queue_event('LOOKUP_CARRIER', {
            'hostmask' : hostmask,
            'number' : number
        })

    def _parse_cmd_reindex(self, hostmask, chan, cmd):
        logging.info('!r %s, %s', hostmask, chan)

        m = re.match(r'^\s*$', cmd, re.UNICODE)
        if not m:
            self._reply(chan, 'Usage: !r(eindex all)')
            return

        self.sms900.queue_event('REINDEX_ALL', {})

    def _parse_cmd_openai_prompt(self, hostmask, chan, cmd):
        logging.info('!op %s, %s', hostmask, chan)

        new_prompt = cmd.strip()
        self.sms900.openai_set_prompt(new_prompt)
        self._reply(chan, 'Kashikomarimashita' if new_prompt else 'Prompt reset')

    def _parse_cmd_openai_reset_history(self, hostmask, chan, cmd):
        logging.info('!or %s, %s', hostmask, chan)

        m = re.match(r'^\s*$', cmd, re.UNICODE)
        if not m:
            self._reply(chan, 'Usage: !or(reset history)')
            return

        self.sms900.openai_reset_history()
        self._reply(chan, 'History reset')

    def _parse_cmd_openai_comment_on_context(self, hostmask, chan, cmd):
        logging.info('!oc %s, %s', hostmask, chan)

        m = re.match(r'^\s*\d+\s*$', cmd, re.UNICODE)
        if not m:
            self._reply(chan, 'Usage: !oc(comment) <number-of-lines>')
            return

        length = int(cmd.strip())

        self.sms900.queue_event('TRIGGER_COMPLETION', {'include_all_length': length})

    def _parse_cmd_openai_model(self, hostmask, chan, cmd):
        logging.info('!om %s, %s', hostmask, chan)

        new_model = cmd.strip()
        self.sms900.queue_event('SET_AI_MODEL', {'model': new_model})

    def _parse_cmd_openai_info(self, hostmask, chan, cmd):
        logging.info('!oi %s, %s', hostmask, chan)

        provider, model = self.sms900.openai_get_info()
        self._reply(chan, f'Current model: {provider} / {model}')

    def _parse_cmd_openai_default(self, hostmask, chan, cmd):
        logging.info('!od %s, %s', hostmask, chan)

        args = cmd.strip()
        if not args:
            self.sms900.queue_event('GET_AI_DEFAULTS', {})
            return

        m = re.match(r'^(\S+)\s+(\S+)\s*$', args, re.UNICODE)
        if not m:
            self._reply(chan, 'Usage: !od [provider model]')
            return

        provider = m.group(1)
        model = m.group(2)
        self.sms900.queue_event('SET_AI_DEFAULT', {'provider': provider, 'model': model})

    def _parse_cmd_timers_list(self, hostmask, chan, cmd):
        logging.info('!tl %s, %s', hostmask, chan)

        m = re.match(r'^\s*$', cmd, re.UNICODE)
        if not m:
            self._reply(chan, 'Usage: !tl(ist)')
            return

        self.sms900.timers_list()

    def _parse_cmd_timers_clear(self, hostmask, chan, cmd):
        logging.info('!tc %s, %s', hostmask, chan)

        m = re.match(r'^\s*(all|[-a-fA-F0-9]{36})\s*$', cmd, re.UNICODE)
        if not m:
            self._reply(chan, 'Usage: !tc(lear) <all|uuid>')
            return

        count = self.sms900.timers_clear(m[1])
        self._reply(chan, f'Cleared {count} active timers')

    def _parse_cmd_help(self, hostmask, chan, cmd):
        self._reply(
            chan,
            'Commands: s(end message), a(add contact), d(elete contact), l(ookup), r(eindex all), h(elp)'
        )


class IRCThread(Thread):
    """ Runs the IRC bot in a background thread using a reactor """
    def __init__(self, sms900, host, port, nick, channel):
        Thread.__init__(self)
        self.bot = IRCBot(sms900, host, port, nick, channel)

    def run(self):
        self.bot.start()

    def send_privmsg(self, target, msg):
        self.bot.send_privmsg(target, msg)
