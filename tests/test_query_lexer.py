import unittest

from query_language.errors import QueryLexicalError
from query_language.lexer import tokenize_query


def types(q):
    return [t.type for t in tokenize_query(q)]


class TestQueryLexer(unittest.TestCase):
    def test_spec_example(self):
        self.assertEqual(types('Call(func.name == "open") AND NOT ancestor(With)'), [
            "IDENTIFIER", "LPAREN", "IDENTIFIER", "DOT", "IDENTIFIER", "EQ",
            "STRING", "RPAREN", "AND", "NOT", "ANCESTOR", "LPAREN",
            "IDENTIFIER", "RPAREN"])

    def test_values(self):
        toks = tokenize_query('"a\\"b" \'c\' 42 -3 2.5 $X $my_var')
        self.assertEqual([t.value for t in toks],
                         ['a"b', "c", 42, -3, 2.5, "$X", "$my_var"])
        self.assertEqual([t.type for t in toks],
                         ["STRING", "STRING", "NUMBER", "NUMBER", "NUMBER",
                          "METAVARIABLE", "METAVARIABLE"])

    def test_operators(self):
        self.assertEqual(types("== != <= >= < >"),
                         ["EQ", "NE", "LE", "GE", "LT", "GT"])

    def test_keywords_both_cases_and_relations(self):
        self.assertEqual(types("AND and OR or NOT not"),
                         ["AND", "AND", "OR", "OR", "NOT", "NOT"])
        self.assertEqual(types("parent ancestor descendant"),
                         ["PARENT", "ANCESTOR", "DESCENDANT"])
        self.assertEqual(types("True False None"), ["TRUE", "FALSE", "NONE"])

    def test_identifier_prefix_not_keyword(self):
        self.assertEqual(types("android parental"), ["IDENTIFIER", "IDENTIFIER"])

    def test_punctuation(self):
        self.assertEqual(types("( ) . ,"), ["LPAREN", "RPAREN", "DOT", "COMMA"])

    def test_multiline_and_comments(self):
        toks = tokenize_query("# note\nCall  # trailing\n  AND\n  Name")
        self.assertEqual([t.type for t in toks], ["IDENTIFIER", "AND", "IDENTIFIER"])
        self.assertEqual([t.lineno for t in toks], [2, 3, 4])
        self.assertEqual(toks[1].col, 2)

    def test_errors(self):
        with self.assertRaises(QueryLexicalError) as cm:
            tokenize_query("Call @")
        self.assertEqual((cm.exception.lineno, cm.exception.column), (1, 5))
        with self.assertRaises(QueryLexicalError) as cm:
            tokenize_query('Call(x == "oops')
        self.assertIn("Unterminated", cm.exception.message)


if __name__ == "__main__":
    unittest.main()
