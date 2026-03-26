import unittest
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))

from sms900 import ai
from sms900.sms900 import SMS900

class TestOpenAiUtils(unittest.TestCase):
    def setUp(self):
        self.instance = ai.OpenAI({
            "openai_api_key": "test-key-123",
            "openai_chat_model": "gpt-4",
        })

    def test_splitlong(self):
        self.assertEqual(
            "xyz",
            self.instance.splitlong("xyz")
        )
        self.assertEqual(
            "  xyz  ",
            self.instance.splitlong("  xyz  ")
        )

        self.instance.max_line_length = 2
        self.assertEqual(
            "xy\nz",
            self.instance.splitlong("xyz")
        )

        self.instance.max_line_length = 10
        self.assertEqual(
            "abcdef\nghijklmnop\nqrstuv",
            self.instance.splitlong("abcdef ghijklmnopqrstuv")
        )

        self.instance.max_line_length = 3
        self.assertEqual(
            "abc\ndef\nghi\njkl\nmno\npqr\nstu\nv",
            self.instance.splitlong("abcdefghijklmnopqrstuv")
        )
        self.assertEqual(
            "abc\ndef\nghi\njkl\nmno\npqr\nstu\nv",
            self.instance.splitlong("abc\ndef\nghi\njkl\nmno\npqr\nstu\nv"),
        )
        self.assertEqual(
            "abc\ndef\nghi\njkl\nmno\npqr\nstu\nv",
            self.instance.splitlong("abcdef\nghijkl\nmnopqr\nstuv"),
        )
        self.assertEqual(
            "ab\ncd\nef\nghi\nj\nkl\nm\nnop\nqr\nst\nuv",
            self.instance.splitlong("ab cd ef\nghij kl\nm nopqr\nst uv"),
        )
        self.assertEqual(
            "ab\n\nxy\n\nz",
            self.instance.splitlong("ab\n\nxy\n\nz"),
        )
        self.assertEqual(
            "\n\nab\n\nxy\n\nz\n\n",
            self.instance.splitlong("\n\nab\n\nxy\n\nz\n\n"),
        )
        self.assertEqual(
            "å\nä\nöa\nbcd\ne",
            self.instance.splitlong("åäöabcde"),
        )

    def test_strip_imaginary_response(self):
        self.assertEqual(
            "abcdefgh\nxyzåäö",
            self.instance.strip_imaginary_response("abcdefgh\nxyzåäö")
        )

        self.assertEqual(
            "abcdefgh",
            self.instance.strip_imaginary_response("abcdefgh\n<kalle> xyzåäö\nok")
        )

class TestFormatIrc(unittest.TestCase):
    def setUp(self):
        self.format_irc = SMS900._format_irc

    def _make_config(self, enabled):
        obj = type('Obj', (), {'config': {'irc_formatting': enabled}})()
        return obj

    def test_bold(self):
        obj = self._make_config(True)
        self.assertEqual('\x02bold\x02', self.format_irc(obj, '**bold**'))

    def test_italic(self):
        obj = self._make_config(True)
        self.assertEqual('\x1ditalic\x1d', self.format_irc(obj, '*italic*'))

    def test_mixed(self):
        obj = self._make_config(True)
        self.assertEqual(
            '\x02bold\x02 and \x1ditalic\x1d',
            self.format_irc(obj, '**bold** and *italic*')
        )

    def test_disabled(self):
        obj = self._make_config(False)
        self.assertEqual('**bold** and *italic*', self.format_irc(obj, '**bold** and *italic*'))

    def test_no_markdown(self):
        obj = self._make_config(True)
        self.assertEqual('plain text', self.format_irc(obj, 'plain text'))

if __name__ == '__main__':
    unittest.main()
