import unittest
import os
import sys

sys.path.insert(0, os.getcwd() + '/..')

import openai

class TestOpenAiUtils(unittest.TestCase):
    def setUp(self):
        self.instance = openai.OpenAI({
            "openai_api_key": 123,
            "openai_engine": 123,
            "openai_use_chat": True,
            "openai_chat_model": 123,
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

if __name__ == '__main__':
    unittest.main()
