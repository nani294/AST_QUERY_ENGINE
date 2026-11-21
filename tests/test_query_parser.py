import unittest

from query_language.errors import QueryError
from query_language.parser import parse_query
from query_language.query_ast import (
    And, Ancestor, Descendant, Literal, MetaVariable, NodeMatch, Not, Or,
    Parent, Predicate,
)

A, B, C = NodeMatch("A", None), NodeMatch("B", None), NodeMatch("C", None)


class TestQueryParser(unittest.TestCase):
    def test_node_match(self):
        self.assertEqual(parse_query("Call"), NodeMatch("Call", None))

    def test_predicate(self):
        q = parse_query('Call(func.name == "open")')
        self.assertEqual(q, NodeMatch("Call", Predicate(["func", "name"], "==", Literal("open"))))

    def test_all_comparison_operators(self):
        for op in ("==", "!=", "<", ">", "<=", ">="):
            q = parse_query(f"FunctionDef(num_params {op} 3)")
            self.assertEqual(q.predicate.op, op)
            self.assertEqual(q.predicate.value, Literal(3))

    def test_literal_values(self):
        self.assertEqual(parse_query("Constant(value == True)").predicate.value, Literal(True))
        self.assertEqual(parse_query("Constant(value == None)").predicate.value, Literal(None))
        self.assertEqual(parse_query("Constant(value == 2.5)").predicate.value, Literal(2.5))

    def test_spec_example_tree(self):
        q = parse_query('Call(func.name == "open") AND NOT ancestor(With)')
        self.assertEqual(q, And(
            NodeMatch("Call", Predicate(["func", "name"], "==", Literal("open"))),
            Not(Ancestor(NodeMatch("With", None)))))

    def test_and_or_not(self):
        self.assertEqual(parse_query("A AND B"), And(A, B))
        self.assertEqual(parse_query("A OR B"), Or(A, B))
        self.assertEqual(parse_query("NOT A"), Not(A))

    def test_precedence(self):
        self.assertEqual(parse_query("A OR B AND C"), Or(A, And(B, C)))
        self.assertEqual(parse_query("A AND B OR C"), Or(And(A, B), C))
        self.assertEqual(parse_query("NOT A AND B"), And(Not(A), B))
        self.assertEqual(parse_query("NOT NOT A"), Not(Not(A)))

    def test_associativity(self):
        self.assertEqual(parse_query("A AND B AND C"), And(And(A, B), C))

    def test_parentheses_override(self):
        self.assertEqual(parse_query("(A OR B) AND C"), And(Or(A, B), C))
        self.assertEqual(parse_query("NOT (A OR B)"), Not(Or(A, B)))

    def test_prefix_relations(self):
        self.assertEqual(parse_query("parent(A)"), Parent(A))
        self.assertEqual(parse_query("ancestor(A)"), Ancestor(A))
        self.assertEqual(parse_query("descendant(A OR B)"), Descendant(Or(A, B)))

    def test_infix_relations(self):
        self.assertEqual(parse_query("A descendant B"), And(A, Descendant(B)))
        self.assertEqual(parse_query("A ancestor B"), And(A, Ancestor(B)))
        self.assertEqual(parse_query("A parent B"), And(A, Parent(B)))
        self.assertEqual(parse_query("A descendant B AND C"), And(And(A, Descendant(B)), C))

    def test_nested_relation_operand(self):
        q = parse_query("A AND ancestor(B AND ancestor(C))")
        self.assertEqual(q, And(A, Ancestor(And(B, Ancestor(C)))))

    def test_metavariable(self):
        q = parse_query("Call(func.name == $X)")
        self.assertEqual(q.predicate.value, MetaVariable("$X"))

    def test_predicate_boolean_logic(self):
        q = parse_query('Call(func.name == "a" OR func.name == "b", num_args > 1)')
        # a comma is AND, which binds tighter than OR:  a OR (b AND c)
        self.assertEqual(type(q.predicate), Or)
        self.assertEqual(type(q.predicate.right), And)
        q2 = parse_query("Call(NOT num_args == 0)")
        self.assertEqual(type(q2.predicate), Not)

    def test_multiline_query(self):
        q = parse_query('(\n  Call(func.name == "eval")\n  OR\n  Call(func.name == "exec")\n)\nAND NOT ancestor(With)')
        self.assertEqual(type(q), And)
        self.assertEqual(type(q.left), Or)

    def test_round_trip_through_str(self):
        for text in ['Call(func.name == "open") AND NOT ancestor(With)',
                     "A OR B AND C", "(A OR B) AND C", "NOT (A OR B)",
                     "FunctionDef AND descendant(For) AND descendant(While)",
                     "Call(func.name == $X AND num_args > 1)"]:
            q = parse_query(text)
            self.assertEqual(parse_query(str(q)), q, text)

    def test_positions_recorded(self):
        q = parse_query("Call\n AND Name")
        self.assertEqual((q.lineno, q.col), (1, 0))
        self.assertEqual((q.right.lineno, q.right.col), (2, 5))


class TestQuerySyntaxErrors(unittest.TestCase):
    def err(self, text):
        with self.assertRaises(QueryError) as cm:
            parse_query(text)
        return cm.exception

    def test_missing_close_paren(self):
        e = self.err('Call(func.name == "x" AND')
        self.assertEqual(e.lineno, 1)
        self.assertEqual(e.unexpected, "end of query")

    def test_unexpected_token_position(self):
        e = self.err("Call) AND Name")
        self.assertEqual((e.lineno, e.column), (1, 4))
        self.assertEqual(e.unexpected, "')'")
        self.assertIn("Query Error", e.format())
        self.assertIn("Unexpected token: ')'", e.format())

    def test_missing_value(self):
        e = self.err("Call(func.name ==)")
        self.assertIn("value", e.expected)

    def test_trailing_operator(self):
        self.err("Call AND")

    def test_empty_query(self):
        self.err("   # only a comment\n")

    def test_lexical_error_is_query_error(self):
        self.err("Call @")


if __name__ == "__main__":
    unittest.main()
