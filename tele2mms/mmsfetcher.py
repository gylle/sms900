import email
import http.client
import logging
from os import path
import re
import tempfile
from urllib.parse import urlencode


class MMSFetcher:
    USER_AGENT = "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:41.0) Gecko/20100101 Firefox/41.0"
    MMS_HOST = 'mms.otp.tele2.se'

    def __init__(self, msisdn, msgid, download_to):
        self.msisdn = msisdn
        self.msgid = msgid
        self.download_to = download_to
        self.cookies = {
            'otp': 'yes',
            'skin': 'light'
        }
        self.referer = 'http://%s/mmbox/otp.html' % self.MMS_HOST

    def download_all(self):
        connection = http.client.HTTPConnection(self.MMS_HOST)
        self._login(connection)
        eml_file = self._download_eml(connection)
        connection.close()

        return self._split_eml(eml_file)

    def _login(self, connection):
        login_url = '/mmbox/otp.html';

        headers = self._get_default_request_headers()
        headers.update({
            'Referer': self.referer,
            'Content-Type': 'application/x-www-form-urlencoded',
            'Cookie': self._dict_to_cookie_string(self.cookies)
        })

        login_data = bytes(urlencode({
            "msisdn": self.msisdn,
            "msgid": self.msgid,
            "subLogin": "Log+In"
        }, safe = '+'), 'ascii')

        connection.request('POST', login_url, login_data, headers)
        response = connection.getresponse()
        _ = response.read()
        self.cookies.update(self._get_cookies_from_response(response))

    def _download_eml(self, connection):
        download_url = '/mmbox/getOtpMedia?id=msg&act=viewmsg&locale=en'

        headers = self._get_default_request_headers()
        headers.update({
            'Referer': self.referer,
            'Cookie': self._dict_to_cookie_string(self.cookies)
        })

        connection.request('GET', download_url, None, headers)
        response = connection.getresponse()
        response_bytes = response.read()

        filename = None
        with tempfile.NamedTemporaryFile(delete=False) as f:
            filename = f.name
            logging.info("Writing eml file to %s.." % filename)
            f.write(response_bytes)

        logging.info("Done, returning %s" % filename)

        return filename

    def _split_eml(self, eml_file):
        with open(eml_file, 'r') as f:
            msg = email.message_from_file(f)

        extracted_files = []
        for part in msg.walk():
            if part.is_multipart():
                continue
            if part.get_content_type() == "application/smil":
                continue

            filename = part.get_filename()
            full_path = path.join(self.download_to, filename)

            with open(full_path, 'w+b') as f:
                logging.info("Writing data to %s.." % full_path)
                f.write(part.get_payload(decode=True))

            extracted_files.append(full_path)

        return extracted_files

    def _get_default_request_headers(self):
        return {
            "User-Agent": self.USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
        }

    def _dict_to_cookie_string(self, d):
        return '; '.join(["%s=%s" % (key, value) for key, value in d.items()])

    def _get_cookies_from_response(self, response):
        cookies = {}
        for key, value in response.msg.items():
            if key == 'Set-Cookie':
                m = re.match('([^=]+)=([^;]+)', value)
                if m:
                    cookies[m.group(1)] = m.group(2)
        return cookies
