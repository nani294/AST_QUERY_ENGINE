"""Source parser: source text -> custom AST (no Python `ast` module)."""
import unittest

from source_parser.errors import SourceError, SourceSyntaxError
from source_parser.parser import parse_source


def first(src):
    return parse_source(src).body[0]


class TestStatements(unittest.TestCase):
    def test_function_and_params(self):
        f = first("def f(a, b=1):\n    return a\n")
        self.assertEqual(f.node_type, "FunctionDef")
        self.assertEqual(f.name, "f")
        self.assertEqual([p.name for p in f.params], ["a", "b"])
        self.assertEqual(f.params[1].default.value, 1)
        self.assertEqual(f.body[0].node_type, "Return")

    def test_assignment(self):
        a = first("x = 10\n")
        self.assertEqual(a.node_type, "Assign")
        self.assertEqual(a.target.id, "x")
        self.assertEqual(a.value.value, 10)

    def test_tuple_assignment(self):
        a = first("a, b = 1, 2\n")
        self.assertEqual(a.target.node_type, "Tuple")
        self.assertEqual(a.value.num_elements, 2)

    def test_if_elif_else(self):
        n = first("if a:\n    x\nelif b:\n    y\nelse:\n    z\n")
        self.assertEqual(n.node_type, "If")
        self.assertFalse(n.is_elif)
        self.assertEqual(n.orelse[0].node_type, "If")
        self.assertTrue(n.orelse[0].is_elif)
        self.assertTrue(n.has_else)

    def test_for_while_with(self):
        self.assertEqual(first("for i in xs:\n    pass\n").node_type, "For")
        self.assertEqual(first("for k, v in xs:\n    pass\n").target.node_type, "Tuple")
        self.assertEqual(first("while x:\n    break\n").node_type, "While")
        w = first("with open(f) as g, h():\n    pass\n")
        self.assertEqual(w.node_type, "With")
        self.assertEqual(w.num_items, 2)
        self.assertEqual(w.items[0].optional_vars.id, "g")

    def test_try_except_finally(self):
        t = first("try:\n    a()\nexcept ValueError as e:\n    pass\nexcept:\n    pass\nfinally:\n    b()\n")
        self.assertEqual(t.node_type, "Try")
        self.assertEqual(t.num_handlers, 2)
        self.assertEqual(t.handlers[0].name, "e")
        self.assertTrue(t.handlers[1].is_bare)
        self.assertTrue(t.has_finally)

    def test_imports(self):
        i = first("import os.path as p, sys\n")
        self.assertEqual([a.name for a in i.names], ["os.path", "sys"])
        self.assertEqual(i.names[0].asname, "p")
        j = first("from a.b import c\n")
        self.assertEqual((j.module, j.is_from, j.names[0].name), ("a.b", True, "c"))

    def test_simple_keywords_and_one_line_body(self):
        n = first("if x: pass\n")
        self.assertEqual(n.body[0].node_type, "Pass")
        loop = first("while x:\n    break\n    continue\n")
        self.assertEqual([s.node_type for s in loop.body], ["Break", "Continue"])

    def test_empty_and_comment_only(self):
        self.assertEqual(parse_source("").body, [])
        self.assertEqual(parse_source("# nothing\n\n").body, [])


class TestExpressions(unittest.TestCase):
    def expr(self, text):
        return first(text + "\n")

    def test_call_attribute_keyword(self):
        c = self.expr("a.b.c(1, k=2)")
        self.assertEqual(c.node_type, "Call")
        self.assertEqual(c.func.qualname, "a.b.c")
        self.assertEqual(c.num_args, 1)
        self.assertEqual(c.keywords[0].arg, "k")

    def test_subscript_and_chaining(self):
        n = self.expr("f(x)[0].y")
        self.assertEqual(n.node_type, "Attribute")
        self.assertEqual(n.value.node_type, "Subscript")

    def test_precedence_arith(self):
        n = self.expr("1 + 2 * 3")
        self.assertEqual(n.op, "+")
        self.assertEqual(n.right.op, "*")
        m = self.expr("(1 + 2) * 3")
        self.assertEqual(m.op, "*")
        self.assertEqual(m.left.op, "+")

    def test_left_associativity(self):
        n = self.expr("a - b - c")
        self.assertEqual(n.left.node_type, "BinaryOp")
        self.assertEqual(n.right.node_type, "Name")

    def test_unary(self):
        n = self.expr("-x")
        self.assertEqual((n.node_type, n.op), ("UnaryOp", "-"))
        self.assertEqual(self.expr("not x").op, "not")

    def test_comparisons(self):
        c = self.expr("a < b <= c")
        self.assertEqual(c.ops, ["<", "<="])
        self.assertEqual(self.expr("a not in b").ops, ["not in"])
        self.assertEqual(self.expr("a is not None").ops, ["is not"])

    def test_boolean_precedence(self):
        n = self.expr("a or b and not c")
        self.assertEqual(n.op, "or")
        self.assertEqual(n.values[1].op, "and")
        self.assertEqual(n.values[1].values[1].op, "not")

    def test_literals(self):
        self.assertEqual(self.expr("[1, 2, 3]").num_elements, 3)
        self.assertEqual(self.expr("[]").num_elements, 0)
        self.assertEqual(self.expr("(1, 2)").node_type, "Tuple")
        self.assertEqual(self.expr("(1,)").num_elements, 1)
        self.assertEqual(self.expr("()").num_elements, 0)
        self.assertIs(self.expr("True").value, True)
        self.assertIsNone(self.expr("None").value)
        self.assertEqual(self.expr("'hi'").value, "hi")
        self.assertEqual(self.expr("2.5").value, 2.5)


class TestPositions(unittest.TestCase):
    def test_call_span_and_snippet(self):
        src = '    f = open("x")\n'.lstrip("\n")
        prog = parse_source("def t():\n    f = open(\"x\")\n")
        call = prog.body[0].body[0].value
        self.assertEqual((call.lineno, call.col_offset), (2, 8))
        self.assertEqual((call.end_lineno, call.end_col_offset), (2, 17))

    def test_parenthesized_span_includes_parens(self):
        n = first("(a + b) * c\n")
        self.assertEqual((n.col_offset, n.end_col_offset), (0, 11))
        self.assertEqual((n.left.col_offset, n.left.end_col_offset), (1, 6))

    def test_compound_ends_at_last_statement(self):
        f = first("def f():\n    x = 1\n    return x\n")
        self.assertEqual((f.lineno, f.end_lineno, f.end_col_offset), (1, 3, 12))

    def test_program_spans_file(self):
        p = parse_source("a\nb\n")
        self.assertEqual((p.lineno, p.end_lineno), (1, 3))


class TestSyntaxErrors(unittest.TestCase):
    def err(self, src):
        with self.assertRaises(SourceError) as cm:
            parse_source(src)
        return cm.exception

    def test_unexpected_paren(self):
        e = self.err("x = )\n")
        self.assertIsInstance(e, SourceSyntaxError)
        self.assertEqual((e.lineno, e.column), (1, 4))
        self.assertEqual(e.unexpected, "')'")
        self.assertEqual(e.expected, "expression")
        self.assertIn("Unexpected token: ')'", e.format())

    def test_missing_colon(self):
        e = self.err("if x\n    y\n")
        self.assertEqual(e.lineno, 1)
        self.assertIn("':'", e.expected)

    def test_unexpected_end_of_file(self):
        e = self.err("x = (1 +")
        self.assertEqual(e.unexpected, "end of line")

    def test_unexpected_indent(self):
        e = self.err("  x = 1\n")
        self.assertIn("indent", e.unexpected)

    def test_bad_assignment_target(self):
        e = self.err("f() = 1\n")
        self.assertIn("Cannot assign", e.message)

    def test_lexical_and_indentation_errors_are_source_errors(self):
        self.err("x = $\n")
        self.err("a:\n        b\n    c\n")

    def test_missing_body(self):
        self.err("def f():\nx = 1\n")


if __name__ == "__main__":
    unittest.main()
