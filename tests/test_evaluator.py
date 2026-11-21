"""Evaluator tests: real parsing + real evaluation, no mocked ASTs."""
import unittest

from engine import run_query
from evaluator.matcher import compare, resolve_path
from evaluator.traversal import Traversal
from source_parser.parser import parse_source

SPEC = '''def process(filename):
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


def lines(src, query):
    return [m.line for m in run_query(src, query).matches]


class TestTraversal(unittest.TestCase):
    def test_parent_and_ancestors(self):
        prog = parse_source("def f():\n    for x in y:\n        g(x)\n")
        t = Traversal(prog)
        call = [n for n in t.nodes if n.node_type == "Call"][0]
        self.assertEqual(t.parent_of(call).node_type, "For")
        self.assertEqual([a.node_type for a in t.ancestors_of(call)],
                         ["For", "FunctionDef", "Program"])
        self.assertIsNone(t.parent_of(prog))

    def test_children_and_descendants(self):
        prog = parse_source("for x in y:\n    g(x)\n")
        t = Traversal(prog)
        loop = prog.body[0]
        self.assertEqual([c.node_type for c in t.children_of(loop)], ["Name", "Name", "Call"])
        self.assertEqual([d.node_type for d in t.descendants_of(loop)],
                         ["Name", "Name", "Call", "Name", "Name"])

    def test_preorder_is_source_order(self):
        prog = parse_source("a = 1\nb = 2\n")
        t = Traversal(prog)
        self.assertEqual([n.node_type for n in t.nodes],
                         ["Program", "Assign", "Name", "Constant", "Assign", "Name", "Constant"])

    def test_deep_tree_does_not_overflow(self):
        src = "x = " + "(" * 150 + "1" + ")" * 150 + "\n"
        self.assertEqual(len(Traversal(parse_source(src)).nodes), 4)


class TestMatcher(unittest.TestCase):
    def test_compare_semantics(self):
        self.assertTrue(compare("==", 1, 1.0))
        self.assertFalse(compare("==", 1, True))       # 1 is not True
        self.assertTrue(compare("!=", "a", "b"))
        self.assertTrue(compare("<", 1, 2))
        self.assertFalse(compare("<", "a", 2))         # mixed types never order
        self.assertFalse(compare(">", None, 1))
        self.assertTrue(compare("<=", "a", "a"))

    def test_resolve_path(self):
        call = parse_source("os.system(x)\n").body[0]
        self.assertEqual(resolve_path(call, ["func", "name"]), (True, "system"))
        self.assertEqual(resolve_path(call, ["func", "qualname"]), (True, "os.system"))
        self.assertEqual(resolve_path(call, ["func", "nope"]), (False, None))
        self.assertEqual(resolve_path(call, ["num_args"]), (True, 1))


class TestSpecIntegration(unittest.TestCase):
    """The end-to-end example from the project description."""

    def test_open_outside_with(self):
        self.assertEqual(lines(SPEC, 'Call(func.name == "open") AND NOT ancestor(With)'), [2])

    def test_eval(self):
        self.assertEqual(lines(SPEC, 'Call(func.name == "eval")'), [8])

    def test_function_descendant_for(self):
        self.assertEqual(lines(SPEC, "FunctionDef descendant For"), [1])

    def test_for_descendant_for(self):
        self.assertEqual(lines(SPEC, "For descendant For"), [4])

    def test_snippets_and_columns(self):
        r = run_query(SPEC, 'Call(func.name == "eval")', "sample.py")
        m = r.matches[0]
        self.assertEqual((m.snippet, m.line, m.column, m.node_type),
                         ("eval(user_input)", 8, 5, "Call"))
        self.assertEqual(r.to_dict()["matches"][0]["snippet"], "eval(user_input)")

    def test_multiline_snippet(self):
        m = run_query(SPEC, "For descendant For").matches[0]
        self.assertEqual(m.snippet, "for item in items:\n        for x in item:\n            print(x)")


class TestLogic(unittest.TestCase):
    SRC = ("eval(a)\nexec(b)\nwith f() as g:\n    eval(c)\n"
           "def h():\n    x = 1\n")

    def test_or(self):
        self.assertEqual(lines(self.SRC, 'Call(func.name == "eval") OR Call(func.name == "exec")'),
                         [1, 2, 4])

    def test_not_ancestor(self):
        self.assertEqual(lines(self.SRC, 'Call(func.name == "eval") AND NOT ancestor(With)'), [1])

    def test_parentheses_and_precedence(self):
        q = '(Call(func.name == "eval") OR Call(func.name == "exec")) AND NOT ancestor(With)'
        self.assertEqual(lines(self.SRC, q), [1, 2])
        # without parentheses AND binds tighter: exec calls match regardless of with
        q2 = 'Call(func.name == "eval") OR Call(func.name == "exec") AND NOT ancestor(With)'
        self.assertEqual(lines(self.SRC, q2), [1, 2, 4])

    def test_not_pushes_to_complement(self):
        self.assertEqual(lines("a()\nb()\n", 'Call AND NOT Call(func.name == "a")'), [2])

    def test_parent_relation(self):
        src = "for x in y:\n    f(x)\n    if x:\n        f(2)\n"
        self.assertEqual(lines(src, "Call AND parent(For)"), [2])
        self.assertEqual(lines(src, "Call AND parent(If)"), [4])

    def test_descendant_relation_with_predicate(self):
        src = "def a():\n    pass\ndef b():\n    return eval(x)\n"
        self.assertEqual(lines(src, 'FunctionDef AND descendant(Call(func.name == "eval"))'), [3])

    def test_not_descendant(self):
        src = "def a():\n    pass\ndef b():\n    return 1\n"
        self.assertEqual(lines(src, "FunctionDef AND NOT descendant(Return)"), [1])

    def test_no_matches(self):
        self.assertEqual(lines("x = 1\n", "Call"), [])

    def test_structure_not_text(self):
        src = '# eval(x)\ns = "eval(x)"\nevaluate(x)\n'
        self.assertEqual(lines(src, 'Call(func.name == "eval")'), [])


class TestAttributes(unittest.TestCase):
    def test_function_metrics(self):
        src = ("def a(x, y):\n    if x:\n        return 1\n    return 2\n"
               "def b():\n    pass\n")
        self.assertEqual(lines(src, "FunctionDef(num_params == 2)"), [1])
        self.assertEqual(lines(src, "FunctionDef(num_returns > 1)"), [1])
        self.assertEqual(lines(src, "FunctionDef(num_statements == 3)"), [1])
        self.assertEqual(lines(src, 'FunctionDef(name == "b")'), [5])
        self.assertEqual(lines(src, "FunctionDef(name != \"b\")"), [1])

    def test_constant_kinds_and_values(self):
        src = 'a = 1\nb = "s"\nc = True\nd = None\n'
        self.assertEqual(lines(src, 'Constant(kind == "int")'), [1])
        self.assertEqual(lines(src, 'Constant(value == "s")'), [2])
        self.assertEqual(lines(src, "Constant(value == True)"), [3])
        self.assertEqual(lines(src, "Constant(value == None)"), [4])
        self.assertEqual(lines("x = 1\n", "Constant(value == True)"), [])

    def test_nested_function_returns_not_double_counted(self):
        src = "def outer():\n    def inner():\n        return 1\n        return 2\n    return 3\n"
        self.assertEqual(lines(src, "FunctionDef(num_returns == 1)"), [1])
        self.assertEqual(lines(src, "FunctionDef(num_returns == 2)"), [2])

    def test_max_nesting_ignores_elif(self):
        src = ("def f(a):\n    if a:\n        pass\n    elif a:\n        pass\n"
               "    elif a:\n        pass\n")
        self.assertEqual(lines(src, "FunctionDef(max_nesting == 1)"), [1])

    def test_has_else_and_is_elif(self):
        src = "if a:\n    pass\nelif b:\n    pass\nelse:\n    pass\n"
        self.assertEqual(lines(src, "If(is_elif == False, has_else == True)"), [1])
        self.assertEqual(lines(src, "If(is_elif == True)"), [3])

    def test_attribute_call_names(self):
        self.assertEqual(lines("os.system(c)\n", 'Call(func.name == "system")'), [1])
        self.assertEqual(lines("os.system(c)\n", 'Call(func.qualname == "os.system")'), [1])
        self.assertEqual(lines("f().g()\n", 'Call(func.qualname == "g")'), [])

    def test_keyword_args(self):
        self.assertEqual(lines('open(f, mode="w")\n', "Call(num_keywords == 1, num_args == 1)"), [1])

    def test_position_attributes(self):
        src = "def f():\n    x = 1\n    y = 2\n"
        self.assertEqual(lines(src, "FunctionDef(line_count == 3)"), [1])
        self.assertEqual(lines(src, "Assign(col_offset == 4)"), [2, 3])


class TestMetavariables(unittest.TestCase):
    def test_binding_per_match(self):
        r = run_query('open("a")\neval(b)\n', "Call(func.name == $X)")
        self.assertEqual([m.bindings for m in r.matches], [{"$X": "open"}, {"$X": "eval"}])
        self.assertEqual(r.to_dict()["matches"][0]["bindings"], {"$X": "open"})

    def test_same_variable_must_agree(self):
        src = "def run(a, b):\n    f(1)\n    g(2)\n"
        # both Calls in one function: $X bound by the first predicate, reused by the second
        q = 'FunctionDef AND descendant(Call(func.name == $X)) AND descendant(Call(func.name == $X))'
        r = run_query(src, q)
        self.assertEqual(len(r.matches), 1)
        # unify across a relationship: $X must equal in both places
        q2 = 'Call(func.name == $X) AND ancestor(FunctionDef(name == $X))'
        r2 = run_query("def f():\n    f()\n    g()\n", q2)
        self.assertEqual([(m.line, m.bindings) for m in r2.matches], [(2, {"$X": "f"})])

    def test_binding_not_leaked_through_not(self):
        r = run_query("f()\n", "Call AND NOT Call(func.name == $X AND num_args > 5)")
        self.assertEqual(r.matches[0].bindings, {})

    def test_no_binding_when_attribute_missing(self):
        r = run_query("x = 1\n", "Call(func.name == $X)")
        self.assertEqual(r.matches, [])

    def test_node_value_binds_as_source_text(self):
        r = run_query("f(a.b)\n", "Call(func == $F)")
        self.assertEqual(r.matches[0].bindings, {"$F": "f"})


class TestJsonShape(unittest.TestCase):
    def test_to_dict_keys(self):
        d = run_query("eval(x)\n", 'Call(func.name == "eval")', "s.py").to_dict()
        self.assertEqual(set(d), {"query", "file", "matches"})
        self.assertEqual(d["query"], 'Call(func.name == "eval")')
        self.assertEqual(d["file"], "s.py")
        self.assertTrue({"node_type", "line", "column", "snippet", "bindings"} <= set(d["matches"][0]))


if __name__ == "__main__":
    unittest.main()
