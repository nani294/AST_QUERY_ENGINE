"""Tests for the source lexer (SLY) and the INDENT/DEDENT layout stage."""
import unittest

from source_parser.errors import LexicalError, SourceIndentationError
from source_parser.lexer import raw_tokens, tokenize


def types(src):
    return [t.type for t in tokenize(src)]


class TestKeywords(unittest.TestCase):
    def test_every_keyword(self):
        words = ("def if elif else for while in return with as try except "
                 "finally import from pass break continue and or not is "
                 "True False None").split()
        for w in words:
            self.assertEqual(types(w), [w.upper(), "NEWLINE"], w)

    def test_keyword_prefix_is_identifier(self):
        self.assertEqual(types("define"), ["IDENTIFIER", "NEWLINE"])
        self.assertEqual(types("iffy"), ["IDENTIFIER", "NEWLINE"])
        self.assertEqual(types("Nonexistent"), ["IDENTIFIER", "NEWLINE"])


class TestLiterals(unittest.TestCase):
    def test_identifier(self):
        tok = tokenize("foo_bar1")[0]
        self.assertEqual((tok.type, tok.value), ("IDENTIFIER", "foo_bar1"))

    def test_numbers(self):
        a, b = tokenize("42")[0], tokenize("3.14")[0]
        self.assertEqual((a.type, a.value), ("NUMBER", 42))
        self.assertEqual((b.type, b.value), ("NUMBER", 3.14))

    def test_strings(self):
        self.assertEqual(tokenize('"hi"')[0].value, "hi")
        self.assertEqual(tokenize("'hi'")[0].value, "hi")
        self.assertEqual(tokenize(r'"a\nb"')[0].value, "a\nb")

    def test_triple_quoted_string_spans_lines(self):
        toks = tokenize('x = """a\nb"""\ny')
        s = [t for t in toks if t.type == "STRING"][0]
        self.assertEqual((s.lineno, s.end_lineno, s.value), (1, 2, "a\nb"))
        y = [t for t in toks if t.value == "y"][0]
        self.assertEqual(y.lineno, 3)


class TestOperators(unittest.TestCase):
    def test_each_operator(self):
        table = {"==": "EQ", "!=": "NE", "<=": "LE", ">=": "GE", "<": "LT",
                 ">": "GT", "=": "ASSIGN", "+": "PLUS", "-": "MINUS",
                 "*": "MULTIPLY", "/": "DIVIDE", "%": "MODULO"}
        for text, name in table.items():
            self.assertEqual(types(f"a {text} b"),
                             ["IDENTIFIER", name, "IDENTIFIER", "NEWLINE"], text)

    def test_two_char_operator_wins(self):
        self.assertEqual(types("a==b"), ["IDENTIFIER", "EQ", "IDENTIFIER", "NEWLINE"])
        self.assertEqual(types("a<=b"), ["IDENTIFIER", "LE", "IDENTIFIER", "NEWLINE"])

    def test_punctuation(self):
        self.assertEqual(types("()[]:,."),
                         ["LPAREN", "RPAREN", "LBRACKET", "RBRACKET",
                          "COLON", "COMMA", "DOT", "NEWLINE"])

    def test_attribute_vs_float(self):
        self.assertEqual(types("a.b"), ["IDENTIFIER", "DOT", "IDENTIFIER", "NEWLINE"])
        self.assertEqual(types("1.5"), ["NUMBER", "NEWLINE"])


class TestIndentation(unittest.TestCase):
    def test_spec_example(self):
        src = "def test():\n    x = 10\n    if x > 5:\n        print(x)\n"
        self.assertEqual(types(src), [
            "DEF", "IDENTIFIER", "LPAREN", "RPAREN", "COLON", "NEWLINE",
            "INDENT", "IDENTIFIER", "ASSIGN", "NUMBER", "NEWLINE",
            "IF", "IDENTIFIER", "GT", "NUMBER", "COLON", "NEWLINE",
            "INDENT", "IDENTIFIER", "LPAREN", "IDENTIFIER", "RPAREN", "NEWLINE",
            "DEDENT", "DEDENT"])

    def test_no_trailing_newline_gets_one(self):
        self.assertEqual(types("if x:\n    y"),
                         ["IF", "IDENTIFIER", "COLON", "NEWLINE",
                          "INDENT", "IDENTIFIER", "NEWLINE", "DEDENT"])

    def test_dedent_back_to_middle_level(self):
        src = "a:\n    b:\n        c\n    d\ne\n"
        t = types(src)
        self.assertEqual(t.count("INDENT"), 2)
        self.assertEqual(t.count("DEDENT"), 2)

    def test_multiple_dedents_in_one_step(self):
        src = "a:\n    b:\n        c\nd\n"
        t = types(src)
        i = t.index("DEDENT")
        self.assertEqual(t[i:i + 3], ["DEDENT", "DEDENT", "IDENTIFIER"])

    def test_blank_and_comment_lines_ignored(self):
        src = "a:\n\n    # note\n    b  # trailing\n\n"
        self.assertEqual(types(src),
                         ["IDENTIFIER", "COLON", "NEWLINE", "INDENT",
                          "IDENTIFIER", "NEWLINE", "DEDENT"])

    def test_newline_inside_brackets_ignored(self):
        self.assertEqual(types("f(a,\n  b)\n"),
                         ["IDENTIFIER", "LPAREN", "IDENTIFIER", "COMMA",
                          "IDENTIFIER", "RPAREN", "NEWLINE"])

    def test_backslash_continuation(self):
        self.assertEqual(types("a + \\\n b\n"),
                         ["IDENTIFIER", "PLUS", "IDENTIFIER", "NEWLINE"])

    def test_windows_line_endings(self):
        self.assertEqual(types("a:\r\n    b\r\n"),
                         ["IDENTIFIER", "COLON", "NEWLINE", "INDENT",
                          "IDENTIFIER", "NEWLINE", "DEDENT"])

    def test_tab_indentation(self):
        self.assertIn("INDENT", types("a:\n\tb\n"))

    def test_inconsistent_dedent_is_error(self):
        with self.assertRaises(SourceIndentationError) as cm:
            tokenize("a:\n        b\n    c\n")
        self.assertEqual(cm.exception.lineno, 3)

    def test_empty_source(self):
        self.assertEqual(tokenize(""), [])


class TestPositions(unittest.TestCase):
    def test_columns_and_ends(self):
        x, eq, one = tokenize("x = 1")[:3]
        self.assertEqual((x.lineno, x.col, x.end_col), (1, 0, 1))
        self.assertEqual((eq.col, eq.end_col), (2, 3))
        self.assertEqual((one.col, one.end_col), (4, 5))

    def test_second_line(self):
        toks = tokenize("a\n    b\n")
        b = [t for t in toks if t.value == "b"][0]
        self.assertEqual((b.lineno, b.col), (2, 4))

    def test_raw_tokens_have_no_indent(self):
        names = [t.type for t in raw_tokens("a:\n    b\n")]
        self.assertNotIn("INDENT", names)
        self.assertNotIn("DEDENT", names)


class TestLexicalErrors(unittest.TestCase):
    def test_illegal_character(self):
        with self.assertRaises(LexicalError) as cm:
            tokenize("x = $")
        self.assertEqual((cm.exception.lineno, cm.exception.column), (1, 4))
        self.assertIn("Illegal character", cm.exception.message)

    def test_unterminated_string(self):
        with self.assertRaises(LexicalError) as cm:
            tokenize('a = 1\nx = "abc')
        self.assertEqual(cm.exception.lineno, 2)
        self.assertIn("Unterminated", cm.exception.message)


class TestRealisticSource(unittest.TestCase):
    def test_process_example_lexes(self):
        src = '''def process(filename):
    f = open(filename)

    for item in items:
        for x in item:
            print(x)

    eval(user_input)

    try:
        risky()
    except:
        pass

    return f
'''
        t = types(src)
        self.assertEqual(t.count("INDENT"), t.count("DEDENT"))
        self.assertEqual(t[:2], ["DEF", "IDENTIFIER"])


if __name__ == "__main__":
    unittest.main()
