"""Tests for helpers that do not need SLY."""
import unittest

from source_parser.tokens import LineIndex, decode_string


class TestLineIndex(unittest.TestCase):
    def test_locate(self):
        li = LineIndex("ab\ncde\n\nf")
        self.assertEqual(li.locate(0), (1, 0))
        self.assertEqual(li.locate(2), (1, 2))   # the '\n' itself
        self.assertEqual(li.locate(3), (2, 0))
        self.assertEqual(li.locate(5), (2, 2))
        self.assertEqual(li.locate(7), (3, 0))   # empty line
        self.assertEqual(li.locate(8), (4, 0))


class TestDecodeString(unittest.TestCase):
    def test_plain(self):
        self.assertEqual(decode_string('"hi"'), "hi")
        self.assertEqual(decode_string("'hi'"), "hi")
        self.assertEqual(decode_string('""'), "")

    def test_escapes(self):
        self.assertEqual(decode_string(r'"a\nb\t\"c\\"'), 'a\nb\t"c\\')
        self.assertEqual(decode_string(r'"\q"'), "\\q")      # unknown escape kept

    def test_triple_quoted(self):
        self.assertEqual(decode_string('"""a\nb"""'), "a\nb")
        self.assertEqual(decode_string("'''x'''"), "x")


if __name__ == "__main__":
    unittest.main()
