from requests_toolbelt import MultipartDecoder
import http.server
import json
import logging
import re
import socketserver
import tempfile
from threading import Thread
import urllib

class SMSHTTPCallbackHandler(http.server.BaseHTTPRequestHandler):
    @classmethod
    def set_sms900(cls, sms900):
        cls.sms900 = sms900

    def do_GET(self):
        self._error()

    def do_POST(self):
        m = re.match('^/api/sms/callback$', self.path)
        if m:
            self._handle_incoming_sms()
            return

        m = re.match('^/api/github/webhook$', self.path)
        if m:
            self._handle_github_webhook()
            return

        m = re.match('^/api/mailgun/incoming$', self.path)
        if m:
            self._handle_mailgun_incoming()
            return

        self._error()

    def _handle_incoming_sms(self):
        data = self._get_post_data()

        print("Got this: %s" % data)

        sender = data["From"][0]
        msg = data["Body"][0]

        logging.info("Sms from: %s" % sender)
        logging.info("Sms content: %s" % msg)

        self.sms900.queue_event('SMS_RECEIVED', {
            'number': sender,
            'msg': msg
        })

        self._generate_response(
            200,
            b'<?xml version="1.0" encoding="UTF-8"?><Response></Response>'
        )

    def _handle_github_webhook(self):
        data = self._get_json_post_data()

        self.sms900.queue_event('GITHUB_WEBHOOK', {
            'data': data
        })

        self._generate_response(200, b'Ok')

    def _handle_mailgun_incoming(self):
        if 'form-data' in self.headers['Content-Type']:
            data = {
                'type': 'form-data',
                'payload':  self._get_post_multipart()
            }
        elif 'x-www-form-urlencoded' in self.headers['Content-Type']:
            data = {
                'type': 'urlencoded',
                'payload': self._get_post_data()
            }
        else:
            logging.error(
                "Unknown content type %s in mailgun handler" % (
                    self.headers['Content-Type']
                )
            )

            self._generate_response(400, b'Unknown Content-Type')
            return

        self.sms900.queue_event('MAILGUN_INCOMING', {
            'data': data
        })

        self._generate_response(200, b'Ok')

    def _get_post_data(self):
        length = int(self.headers['Content-Length'])
        return urllib.parse.parse_qs(self.rfile.read(length).decode('utf-8'))

    def _get_post_multipart(self):
        length = int(self.headers['Content-Length'])
        logging.info("Receiving multipart message")
        data = self.rfile.read(length)

        with tempfile.NamedTemporaryFile(delete=False) as f:
            logging.info("Saving debug data to %s" % f.name)

            f.write(b"POST /api/mailgun/incoming HTTP/1.1\n")
            for header in self.headers.keys():
                f.write(("%s: %s\n" % (header, self.headers[header])).encode('utf-8', 'ignore'))
            f.write(b"\n")
            f.write(data)

        return MultipartDecoder(data, self.headers['Content-Type'])

    def _get_json_post_data(self):
        length = int(self.headers['Content-Length'])
        return json.loads(self.rfile.read(length).decode('utf-8'))

    def _error(self):
        self._generate_response(404, b'Error')

    def _generate_response(self, code, msg, type = 'text/xml'):
        self.send_response(code)
        self.send_header("Content-type", type)
        self.end_headers()
        self.wfile.write(msg)

class ThreadedHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    """ Threaded server """

class HTTPThread(Thread):
    def __init__(self, sms900, server_address):
        Thread.__init__(self)
        SMSHTTPCallbackHandler.set_sms900(sms900)
        self.httpd = ThreadedHTTPServer(server_address, SMSHTTPCallbackHandler)

    def run(self):
        self.httpd.serve_forever()
