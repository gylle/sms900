import http.server
import json
import logging
import re
import socketserver
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

    def _get_post_data(self):
        length = int(self.headers['Content-Length'])
        return urllib.parse.parse_qs(self.rfile.read(length).decode('utf-8'))

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
