import unittest
import os
import sys

sys.path.insert(0, os.getcwd() + '/..')

import ai

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

if __name__ == '__main__':
    unittest.main()
