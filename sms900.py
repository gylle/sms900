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
from ircthread import IRCThread
from http_interface import HTTPThread
from tele2mms.mmsfetcher import MMSFetcher

class SMS900InvalidNumberFormatException(Exception):
    pass

class SMS900():
    def __init__(self, configuration_path):
        self.configuration_path = configuration_path
        self.events = queue.Queue();

    def run(self):
        self._load_configuration()
        self._init_database()
        self.pb = PhoneBook(self.dbconn)

        logging.info("Starting IRCThread thread")
        self.irc_thread = IRCThread(self,
                                    self.config['server'],
                                    self.config['server_port'],
                                    self.config['nickname'],
                                    self.config['channel'])
        self.irc_thread.start()

        logging.info("Starting webserver")
        http_thread = HTTPThread(self, ('0.0.0.0', 8090))
        http_thread.start()

        logging.info("Starting main loop")
        self._main_loop()

    def _load_configuration(self):
        with open(self.configuration_path, 'r') as f:
            self.config = json.load(f)

        # FIXME: Check that we got everything we'll be needing

    def _init_database(self):
        self.dbconn = sqlite3.connect('sms900.db', isolation_level = None)
        c = self.dbconn.cursor()

        try:
            c.execute(
                "create table phonebook ("
                "  id integer primary key,"
                "  nickname text UNIQUE,"
                "  number text UNIQUE"
                ")"
            )
        except Exception as e:
            logging.info("Failed to create table(s): %s" % e)

    def queue_event(self, event_type, data):
        event = {'event_type': event_type}
        event.update(data)
        self.events.put(event)

    def _main_loop(self):
        while True:
            event = self.events.get()
            self._handle_event(event)

    def _handle_event(self, event):
        try:
            logging.info('EVENT: %s' % event)

            if event['event_type'] == 'SEND_SMS':
                sender_hm = event['hostmask']
                number = self._get_number_from_nickname_or_number(event['number'])
                nickname = self._get_nickname_from_hostmask(sender_hm)
                # FIXME: Check the sender
                msg = "<%s> %s" % (nickname, event['msg'])

                self._send_sms(number, msg, sender_hm, )
            elif event['event_type'] == 'ADD_PB_ENTRY':
                number = self._get_canonicalized_number(event['number'])
                nickname = event['nickname']

                self.pb.add_number(nickname, number)
                self._send_privmsg(self.config['channel'], 'Added %s with number %s' % (nickname, number))
            elif event['event_type'] == 'DEL_PB_ENTRY':
                nickname = event['nickname']
                oldnumber = self.pb.get_number(nickname)

                self.pb.del_entry(nickname)
                self._send_privmsg(self.config['channel'], 'Removed contact %s (number: %s)' % (nickname, oldnumber))
            elif event['event_type'] == 'LOOKUP_CARRIER':
                number = event['number']
                number = self._get_canonicalized_number(number)
                self._lookup_carrier(number)
            elif event['event_type'] == 'SMS_RECEIVED':
                number = event['number']
                sms_msg = event['msg']
                sender = self.pb.get_nickname(number)

                m = re.search('ett MMS.+hamtamms.+koden ([^ ]+)', event['msg'])
                if m:
                    self._download_mms(sender, m.group(1))
                    return

                msg = '<%s> %s' % (sender, sms_msg)
                self._send_privmsg(self.config['channel'], msg)

        except (SMS900InvalidNumberFormatException, SMS900InvalidAddressbookEntry) as e:
            self._send_privmsg(self.config['channel'], "Error: %s" % e)
        except Exception as e:
            self._send_privmsg(self.config['channel'], "Unknown error: %s" % e)
            traceback.print_exc()

    def _send_sms(self, number, message, sender_hm):
        logging.info('Sending sms ( %s -> %s )' % (message, number))

        try:
            client = TwilioRestClient(self.config['twilio_account_sid'], self.config['twilio_auth_token'])

            message_data = client.messages.create(
	        to = number,
	        from_ = self.config['twilio_number'],
	        body = message,
            )
            self._send_privmsg(
                self.config['channel'],
                "Sent %s sms to number %s" % (message_data.num_segments, number)
            )
        except twilio.TwilioRestException as e:
            self._send_privmsg(self.config['channel'], "Failed to send sms: %s" % e)

    def _lookup_carrier(self, number):
        logging.info('Looking up number %s' % number)

        try:
            client = TwilioLookupsClient(self.config['twilio_account_sid'], self.config['twilio_auth_token'])

            number_data = client.phone_numbers.get(
                number,
                include_carrier_info=True,
            )

            self._send_privmsg(
                self.config['channel'],
                '%s is %s, carrier: %s' % (number, number_data.carrier['type'], number_data.carrier['name'])
            )
        except twilio.TwilioRestException as e:
            self._send_privmsg(self.config['channel'], "Failed to lookup number: %s" % e)

    def _send_privmsg(self, target, msg):
        self.irc_thread.send_privmsg(target, msg)

    def _get_canonicalized_number(self, number):
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

    def _get_number_from_nickname_or_number(self, number_or_name):
        try:
            number_or_name = self._get_canonicalized_number(number_or_name)

        except SMS900InvalidNumberFormatException:
            try:
                number_or_name = self.pb.get_number(number_or_name)
            except SMS900InvalidAddressbookEntry as e2:
                raise SMS900InvalidNumberFormatException(
                    "%s is not a valid number or existing nickname: %s" % (number_or_name, e2)
                )

        return number_or_name;

    def _get_nickname_from_hostmask(self, hostmask):
        m = re.match('^([^\!]+)', hostmask)
        if not m:
            # FIXME
            return hostmask
        else:
            return m.group(1)

    def _download_mms(self, sender, code):
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

        mms_summary, summary_contains_all = self._get_mms_summary(base_url, files)
        if mms_summary:
            self._send_privmsg(
                self.config['channel'],
                "[MMS] <%s> %s" % (sender, mms_summary)
            )

        if not summary_contains_all:
            self._send_privmsg(
                self.config['channel'],
                "Received %d file(s): %s" % (len(files), base_url)
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
                parts = [text, img_url]
                message = ", ".join([p for p in parts if p])
                summary_contains_all = (len(parts) == len(files))
                return message, summary_contains_all

        except Exception:
            traceback.print_exc()

        return None, False
