import json
import logging
from os import mkdir, path
import queue
import re
import sys
import traceback
import uuid

import twilio
from twilio.rest import TwilioRestClient
from twilio.rest.lookups import TwilioLookupsClient

import sqlite3

from phonebook import PhoneBook, SMS900InvalidAddressbookEntry
from stats import SMSStats
from ircthread import IRCThread
from http_interface import HTTPThread
from tele2mms.mmsfetcher import MMSFetcher

class SMS900InvalidNumberFormatException(Exception):
    pass

class SMS900():
    def __init__(self, configuration_path):
        self.load_configuration(configuration_path)
        self.init_database()
        self.pb = PhoneBook(self.dbconn)
        self.stats = SMSStats(self.dbconn)
        self.events = queue.Queue();

    def load_configuration(self, configuration_path):
        with open(configuration_path, 'r') as f:
            self.config = json.load(f)

        # FIXME: Check that we got everything we'll be needing

    def init_database(self):
        self.dbconn = sqlite3.connect('sms900.db', isolation_level = None)
        c = self.dbconn.cursor()

        try:
            c.execute(
                "create table smslog ("
                "  id integer primary key,"
                "  timestamp integer,"
                "  sender text,"
                "  recipient text,"
                "  contents text,"
                "  direction text,"
                " sms_count integer"
                ")"
            )
            c.execute(
                "create table phonebook ("
                "  id integer primary key,"
                "  nickname text UNIQUE,"
                "  number text UNIQUE"
                ")"
            )
        except Exception as e:
            logging.info("Failed to create table(s): %s" % e)

    def run(self):
        logging.info("Creating IRCThread instance")
        self.irc_thread = IRCThread(self,
                                    self.config['server'],
                                    self.config['server_port'],
                                    self.config['nickname'],
                                    self.config['channel'])

        logging.info("Starting IRCThread thread")
        self.irc_thread.start()

        logging.info("Starting webserver")
        http_thread = HTTPThread(self, ('0.0.0.0', 8090))
        http_thread.start()

        logging.info("Starting main loop")
        while True:
            event = self.events.get()
            self.handle_event(event)

    def add_event(self, event):
        self.events.put(event)

    def handle_event(self, event):
        try:
            if event['event_src'] == 'IRC':
                self.handle_irc_event(event)
            elif event['event_src'] == 'SMS':
                self.handle_sms_event(event)
            else:
                logging.info('UNKNOWN EVENT: %s' % event)

        except SMS900InvalidNumberFormatException as e:
            self.send_privmsg(self.config['channel'], "Error: %s" % e)
        except SMS900InvalidAddressbookEntry as e:
            self.send_privmsg(self.config['channel'], "Error: %s" % e)
        except Exception as e:
            self.send_privmsg(self.config['channel'], "Unknown error: %s" % e)
            traceback.print_exc()

    def handle_irc_event(self, event):
        logging.info('EVENT from irc: %s' % event)

        if event['event_type'] == 'SEND_SMS':
            sender_hm = event['hostmask']
            number = self.lookup_number(event['number'])
            nickname = self.get_nickname_from_hostmask(sender_hm)
            # FIXME: Check the sender
            msg = "<%s> %s" % (nickname, event['msg'])

            self.send_sms(number, msg, sender_hm, )
        elif event['event_type'] == 'ADD_PB_ENTRY':
            number = self.canonicalize_number(event['number'])
            nickname = event['nickname']

            self.pb.add_number(nickname, number)
            self.send_privmsg(self.config['channel'], 'Added %s with number %s' % (nickname, number))
        elif event['event_type'] == 'DEL_PB_ENTRY':
            nickname = event['nickname']
            oldnumber = self.pb.get_number(nickname)

            self.pb.del_entry(nickname)
            self.send_privmsg(self.config['channel'], 'Removed contact %s (number: %s)' % (nickname, oldnumber))
        elif event['event_type'] == 'SHOW_STATS':
            msgs = self.generate_stats()
            for msg in msgs:
                self.send_privmsg(self.config['channel'], msg)

        elif event['event_type'] == 'LOOKUP_NUMBER':
            number = event['number']
            number = self.canonicalize_number(number)
            self.lookup_carrier(number)

    def handle_sms_event(self, event):
        logging.info('EVENT from SMS: %s' % event)

        if event['event_type'] == 'SMS_RECEIVED':
            number = event['number']
            sms_msg = event['msg']
            sender = self.lookup_nickname(number)

            m = re.search('ett MMS.+hamtamms.+koden ([^ ]+)', event['msg'])
            if m:
                self._download_mms(sender, m.group(1))
                return

            msg = '<%s> %s' % (sender, sms_msg)
            self.send_privmsg(self.config['channel'], msg)

            message_logged = self.stats.log_incoming_message(number, sms_msg)
            if not message_logged:
                self.send_privmsg(self.config['channel'], "Error when logging message: %s" % e)

    def generate_stats(self):
        stats = self.stats.get_statistics()
        msg = "Total in: %d, total out: %d" % (stats['total_in'], stats['total_out'])
        return [msg]

    def send_sms(self, number, message, sender_hm):
        logging.info('Sending sms ( %s -> %s )' % (message, number))

        try:
            client = TwilioRestClient(self.config['twilio_account_sid'], self.config['twilio_auth_token'])

            message_data = client.messages.create(
	        to = number,
	        from_ = self.config['twilio_number'],
	        body = message,
            )
            self.send_privmsg(
                self.config['channel'],
                "Sent %s sms to number %s" % (message_data.num_segments, number)
            )

            message_logged = self.stats.log_outgoing_message(
                sender_hm,
                number,
                message,
                int(message_data.num_segments)
            )
            if not message_logged:
                self.send_privmsg(self.config['channel'], "Failed to log outgoing sms: %s" % e)

        except twilio.TwilioRestException as e:
            self.send_privmsg(self.config['channel'], "Failed to send sms: %s" % e)

    def lookup_carrier(self, number):
        logging.info('Looking up number %s' % number)

        try:
            client = TwilioLookupsClient(self.config['twilio_account_sid'], self.config['twilio_auth_token'])

            number_data = client.phone_numbers.get(
                number,
                include_carrier_info=True,
            )

            self.send_privmsg(
                self.config['channel'],
                '%s is %s, carrier: %s' % (number, number_data.carrier['type'], number_data.carrier['name'])
            )
        except twilio.TwilioRestException as e:
            self.send_privmsg(self.config['channel'], "Failed to lookup number: %s" % e)

    def send_privmsg(self, target, msg):
        self.irc_thread.send_privmsg(target, msg)

    def canonicalize_number(self, number):
        m = re.match('^\+[0-9]+$', number)
        if m:
            logging.info('number %s already canonicalized, returning as is' % number)
            return number

        m = re.match('^0(7[0-9]{8})$', number)
        if m:
            new_number = '+46%s' % m.group(1)
            logging.info('number %s was canonicalized and returned as %s' % (number, new_number))
            return new_number

        raise SMS900InvalidNumberFormatException("%s is not a valid number" % number)

    def lookup_number(self, number_or_name):
        try:
            number_or_name = self.canonicalize_number(number_or_name)

        except SMS900InvalidNumberFormatException:
            try:
                number_or_name = self.pb.get_number(number_or_name)
            except SMS900InvalidAddressbookEntry as e2:
                raise SMS900InvalidNumberFormatException(
                    "%s is not a valid number or existing nickname: %s" % (number_or_name, e2)
                )

        return number_or_name;

    def lookup_nickname(self, number):
        try:
            nickname = self.pb.get_nickname(number)
            return nickname
        except SMS900InvalidAddressbookEntry:
            return number

    def get_nickname_from_hostmask(self, hostmask):
        m = re.match('^([^\!]+)', hostmask)
        if not m:
            # FIXME
            return hostmask
        else:
            return m.group(1)

    def _download_mms(self, sender, code):
        self.send_privmsg(self.config['channel'], "MMS from %s, downloading.." % sender)

        rel_path = str(uuid.uuid4())
        save_path = path.join(
            self.config['mms_save_path'],
            rel_path
        )

        mkdir(save_path)

        # FIXME: Hack.
        msisdn = self.config['twilio_number'].replace('+46', '0')
        fetcher = MMSFetcher(msisdn, code, save_path)
        files = fetcher.download_all()

        base_url = "%s/%s" % (
            self.config['external_mms_url'],
            rel_path
        )

        mms_summary = self._get_mms_summary(base_url, files)
        if mms_summary:
            self.send_privmsg(
                self.config['channel'],
                "<%s> %s" % (sender, mms_summary)
            )

        self.send_privmsg(
            self.config['channel'],
            " (Received %d file(s): %s)" % (len(files), base_url)
        )

    def _get_mms_summary(self, base_url, files):
        try:
            text = None
            img_url = None

            # Find the first text and the first image file, if any
            for full_path in files:
                m = re.search('\.([^.]+)$', full_path)
                if m:
                    if not img_url:
                        if m.group(1) in ['jpg', 'jpeg', 'png']:
                            filename = path.basename(full_path)
                            img_url = "%s/%s" % (base_url, filename)

                    if not text:
                        if m.group(1) in ['txt']:
                            with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                                text = f.read()

            if text or img_url:
                return ", ".join([p for p in [text, img_url] if p])

        except Exception:
            traceback.print_exc()

        return None
