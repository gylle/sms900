""" The main bot module for sms900 """
import json
import logging
import queue
import re
import traceback
import uuid
from os import mkdir, path

import sqlite3

import twilio
from twilio.rest import TwilioRestClient
from twilio.rest.lookups import TwilioLookupsClient

from phonebook import PhoneBook, SMS900InvalidAddressbookEntry
from ircthread import IRCThread
from http_interface import HTTPThread


class SMS900InvalidNumberFormatException(Exception):
    """ Simple exception to use for invalid number inputs"""
    pass


class SMS900():
    """ The main class to use """
    def __init__(self, configuration_path):
        """ The init method for the main class.
        Should probably add an example or two here.
        """
        self.configuration_path = configuration_path
        self.events = queue.Queue()
        self.config = None
        self.dbconn = None
        self.irc_thread = None
        self.pb = None

    def run(self):
        """ Starts the main loop"""
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
        with open(self.configuration_path, 'r') as file:
            self.config = json.load(file)

        # FIXME: Check that we got everything we'll be needing

    def _init_database(self):
        self.dbconn = sqlite3.connect('sms900.db', isolation_level=None)
        conn = self.dbconn.cursor()

        try:
            conn.execute(
                "create table phonebook ("
                "  id integer primary key,"
                "  nickname text UNIQUE,"
                "  number text UNIQUE"
                ")"
            )
        except sqlite3.Error as err:
            logging.info("Failed to create table(s): %s", err)

    def queue_event(self, event_type, data):
        """ queues event, stupid doc string i know """
        event = {'event_type': event_type}
        event.update(data)
        self.events.put(event)

    def _main_loop(self):
        while True:
            event = self.events.get()
            self._handle_event(event)

    def _handle_event(self, event):
        try:
            logging.info('EVENT: %s', event)

            if event['event_type'] == 'SEND_SMS':
                sender_hm = event['hostmask']
                number = self._get_num_from_nick_or_num(event['number'])
                nickname = self._get_nickname_from_hostmask(sender_hm)
                # FIXME: Check the sender
                msg = "<%s> %s" % (nickname, event['msg'])

                self._send_sms(number, msg)
            elif event['event_type'] == 'ADD_PB_ENTRY':
                number = self._get_canonicalized_number(event['number'])
                nickname = event['nickname']

                self.pb.add_number(nickname, number)
                self._send_privmsg(self.config['channel'],
                                   'Added %s with number %s' % (nickname, number))
            elif event['event_type'] == 'DEL_PB_ENTRY':
                nickname = event['nickname']
                oldnumber = self.pb.get_number(nickname)

                self.pb.del_entry(nickname)
                self._send_privmsg(self.config['channel'],
                                   'Removed contact %s (number: %s)' % (nickname, oldnumber))
            elif event['event_type'] == 'LOOKUP_CARRIER':
                number = event['number']
                number = self._get_canonicalized_number(number)
                self._lookup_carrier(number)
            elif event['event_type'] == 'SMS_RECEIVED':
                number = event['number']
                sms_msg = event['msg']
                try:
                    sender = self.pb.get_nickname(number)
                except SMS900InvalidAddressbookEntry:
                    sender = number

                msg = '<%s> %s' % (sender, sms_msg)
                self._send_privmsg(self.config['channel'], msg)
            elif event['event_type'] == 'GITHUB_WEBHOOK':
                self._handle_github_event(event['data'])

        except (SMS900InvalidNumberFormatException,
                SMS900InvalidAddressbookEntry) as err:
            self._send_privmsg(self.config['channel'], "Error: %s" % err)
        except Exception as err:
            self._send_privmsg(self.config['channel'], "Unknown error: %s" %
                               err)
            traceback.print_exc()

    def _send_sms(self, number, message):
        logging.info('Sending sms ( %s -> %s )', message, number)

        try:
            client = TwilioRestClient(self.config['twilio_account_sid'],
                                      self.config['twilio_auth_token'])

            message_data = client.messages.create(to=number,
                                                  from_=self.config['twilio_number'],
                                                  body=message,)

            self._send_privmsg(self.config['channel'],
                               "Sent %s sms to number %s"
                               % (message_data.num_segments, number))
        except twilio.TwilioRestException as err:
            self._send_privmsg(self.config['channel'],
                               ("Failed to send sms: %s", err))

    def _lookup_carrier(self, number):
        logging.info('Looking up number %s', number)

        try:
            client = TwilioLookupsClient(self.config['twilio_account_sid'],
                                         self.config['twilio_auth_token'])

            number_data = client.phone_numbers.get(number,
                                                   include_carrier_info=True)

            self._send_privmsg(self.config['channel'],
                               '%s is %s, carrier: %s'
                               % (number,
                                  number_data.carrier['type'],
                                  number_data.carrier['name']))
        except twilio.TwilioRestException as err:
            self._send_privmsg(self.config['channel'],
                               "Failed to lookup number: %s" % err)

    def _send_privmsg(self, target, msg):
        self.irc_thread.send_privmsg(target, msg)

    def _get_canonicalized_number(self, number):
        match = re.match(r'^\+[0-9]+$', number)
        if match:
            logging.info('number %s already canonicalized, returning as is',
                         number)
            return number

        match = re.match(r'^0(7[0-9]{8})$', number)
        if match:
            new_number = '+46%s' % match.group(1)
            logging.info('number %s was canonicalized and returned as %s',
                         number,
                         new_number)
            return new_number

        raise SMS900InvalidNumberFormatException("%s is not a valid number",
                                                 number)

    def _get_num_from_nick_or_num(self, number_or_name):
        try:
            number_or_name = self._get_canonicalized_number(number_or_name)

        except SMS900InvalidNumberFormatException:
            try:
                number_or_name = self.pb.get_number(number_or_name)
            except SMS900InvalidAddressbookEntry as err2:
                raise SMS900InvalidNumberFormatException(
                    "%s is not a valid number or existing nickname: %s"
                    % (number_or_name, err2))

        return number_or_name

    def _get_nickname_from_hostmask(self, hostmask):
        nick = re.match(r'^([^\!]+)', hostmask)
        if not nick:
            # FIXME
            return hostmask
        else:
            return nick.group(1)

    def _handle_github_event(self, data):
        try:
            repository_name = data['repository']['full_name']

            for commit in data['commits']:
                self._send_privmsg(
                    self.config['channel'],
                    "[%s] %s (%s)" % (
                        repository_name,
                        commit['message'],
                        commit['author']['username']
                    )
                )

        except KeyError as err:
            logging.exception("Failed to parse data from github webhook, reason: %s", err)
