import unittest

from query_language.errors import QuerySemanticError
from query_language.parser import parse_query
from query_language.semantic import analyze


def issues(text):
    with_err = None
    try:
        analyze(parse_query(text))
    except QuerySemanticError as exc:
        with_err = exc
    return with_err


class TestValidQueries(unittest.TestCase):
    def test_valid_queries_pass(self):
        for q in ['Call', 'Call(func.name == "open")', 'FunctionDef(name == "main")',
                  'Name(id == "password")', 'FunctionDef(num_params >= 3)',
                  'Call(func.name == $X)', 'ExceptHandler(is_bare == True)',
                  'While(test.value == True)', 'ExceptHandler(type == None)',
                  'Call(func.qualname == "os.system")',
                  'FunctionDef descendant For',
                  'Call AND NOT ancestor(With)',
                  '(Call OR Name) AND parent(For)',
                  'Constant(value == 5)', 'Alias(name == "x")']:
            self.assertIsNone(issues(q), q)

    def test_every_node_type_from_the_spec(self):
        for t in ["Program", "FunctionDef", "Call", "For", "While", "If", "With",
                  "Assign", "Return", "Name", "Constant", "Try", "ExceptHandler"]:
            self.assertIsNone(issues(t), t)


class TestInvalidNodesAndAttributes(unittest.TestCase):
    def test_unknown_node(self):
        e = issues("UnknownNode")
        self.assertIn("Unknown AST node type 'UnknownNode'", e.format())
        self.assertTrue(e.format().startswith("Semantic Error:"))

    def test_suggestion(self):
        self.assertIn("Did you mean 'Call'?", issues("Cal").format())

    def test_unknown_node_inside_relation(self):
        self.assertIn("Banana", issues("Call AND ancestor(Banana)").format())

    def test_unknown_attribute(self):
        e = issues('Call(colour == "red")')
        self.assertIn("no attribute 'colour'", e.format())
        self.assertIn("Available attributes", e.format())

    def test_unknown_nested_attribute(self):
        self.assertIn("Invalid attribute path", issues('Call(func.nme == "x")').format())

    def test_attribute_through_non_node(self):
        self.assertIn("not a node", issues('FunctionDef(name.first == "x")').format())

    def test_multiple_errors_reported_together(self):
        e = issues('Foo AND Bar')
        self.assertEqual(len(e.issues), 2)


class TestOperatorsAndValues(unittest.TestCase):
    def test_type_mismatches(self):
        self.assertIsNotNone(issues('FunctionDef(num_params == "three")'))
        self.assertIsNotNone(issues('Name(id == 5)'))
        self.assertIsNotNone(issues('ExceptHandler(is_bare == "yes")'))

    def test_ordering_operators_need_numbers_or_strings(self):
        self.assertIsNotNone(issues('ExceptHandler(is_bare > 1)'))
        self.assertIsNotNone(issues('FunctionDef(num_params < "a")'))
        self.assertIsNone(issues('Name(id < "m")'))

    def test_metavariable_only_with_equality(self):
        e = issues("Call(num_args > $N)")
        self.assertIn("can only be used with '=='", e.format())


class TestRelationships(unittest.TestCase):
    def test_program_cannot_be_descendant(self):
        self.assertIsNotNone(issues("Call AND descendant(Program)"))

    def test_program_has_no_ancestors(self):
        self.assertIsNotNone(issues("Program AND ancestor(For)"))
        self.assertIsNotNone(issues("Program AND parent(For)"))

    def test_leaf_nodes_have_no_descendants(self):
        e = issues("Name descendant For")
        self.assertIn("never have descendants", e.format())

    def test_valid_relationships(self):
        self.assertIsNone(issues("For AND ancestor(FunctionDef)"))
        self.assertIsNone(issues("Name AND parent(Call)"))

    def test_query_must_select_a_node(self):
        self.assertIsNotNone(issues("NOT ancestor(With)"))
        self.assertIsNotNone(issues("ancestor(With)"))
        self.assertIsNotNone(issues("Call OR ancestor(With)"))
        self.assertIsNone(issues("Call OR Name"))


if __name__ == "__main__":
    unittest.main()
