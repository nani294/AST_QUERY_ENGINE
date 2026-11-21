"""The user-test-case runner: PASS, FAIL, bad inputs, discovery, templates."""
import json
import os
import tempfile
import unittest

import case_runner


def _write(path, text):
    with open(path, "w") as f:
        f.write(text)


def make_case(root, name, source=None, query=None, expected=None, raw_expected=None):
    d = os.path.join(root, name)
    os.makedirs(d)
    if source is not None:
        _write(os.path.join(d, "input.py"), source)
    if query is not None:
        _write(os.path.join(d, "query.query"), query)
    if expected is not None:
        _write(os.path.join(d, "expected.json"), json.dumps(expected))
    if raw_expected is not None:
        _write(os.path.join(d, "expected.json"), raw_expected)
    return d


class TestRunCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_pass(self):
        d = make_case(self.root, "ok", 'def t():\n    f = open("d")\n    return f\n',
                      'Call(func.name == "open") AND NOT ancestor(With)',
                      {"expected_matches": 1})
        r = case_runner.run_case(d)
        self.assertTrue(r.passed)
        text = case_runner.format_case(r)
        self.assertIn("Source parsing: PASS", text)
        self.assertIn("Query parsing: PASS", text)
        self.assertIn("Semantic validation: PASS", text)
        self.assertIn("Evaluation: PASS", text)
        self.assertIn("Expected matches: 1", text)
        self.assertIn("Actual matches:   1", text)
        self.assertIn("TEST PASSED", text)

    def test_fail_wrong_count(self):
        d = make_case(self.root, "bad", "f()\n", "Call", {"expected_matches": 2})
        r = case_runner.run_case(d)
        self.assertFalse(r.passed)
        text = case_runner.format_case(r)
        self.assertIn("TEST FAILED", text)
        self.assertIn("Expected matches: 2", text)
        self.assertIn("Actual matches:   1", text)

    def test_expected_lines_checked(self):
        d = make_case(self.root, "lines", "f()\ng()\n", "Call",
                      {"expected_matches": 2, "expected_lines": [1, 3]})
        self.assertFalse(case_runner.run_case(d).passed)

    def test_expected_bindings_checked(self):
        d = make_case(self.root, "bind", "f()\n", "Call(func.name == $X)",
                      {"expected_matches": 1, "expected_bindings": [{"$X": "f"}]})
        self.assertTrue(case_runner.run_case(d).passed)

    def test_invalid_source_fails_the_test(self):
        d = make_case(self.root, "src", "def (:\n", "Call", {"expected_matches": 0})
        r = case_runner.run_case(d)
        self.assertFalse(r.passed)
        self.assertEqual(r.stages["Source parsing"], "FAIL")
        self.assertEqual(r.stages["Query parsing"], "SKIPPED")
        self.assertIn("Syntax Error", case_runner.format_case(r))

    def test_invalid_query_fails_the_test(self):
        d = make_case(self.root, "q", "x = 1\n", "Call(", {"expected_matches": 0})
        r = case_runner.run_case(d)
        self.assertFalse(r.passed)
        self.assertEqual(r.stages["Query parsing"], "FAIL")

    def test_semantic_error_fails_the_test(self):
        d = make_case(self.root, "sem", "x = 1\n", "UnknownNode", {"expected_matches": 0})
        r = case_runner.run_case(d)
        self.assertFalse(r.passed)
        self.assertEqual(r.stages["Semantic validation"], "FAIL")
        self.assertIn("Unknown AST node type", case_runner.format_case(r))

    def test_expected_error_makes_failures_pass(self):
        for name, src, q, kind in [("a", "def (:\n", "Call", "source"),
                                   ("b", "x\n", "Call(", "query"),
                                   ("c", "x\n", "Nope", "semantic")]:
            d = make_case(self.root, name, src, q, {"expected_error": kind})
            self.assertTrue(case_runner.run_case(d).passed, name)

    def test_expected_error_but_success_fails(self):
        d = make_case(self.root, "x", "f()\n", "Call", {"expected_error": "semantic"})
        self.assertFalse(case_runner.run_case(d).passed)

    def test_missing_files(self):
        d = make_case(self.root, "m", "x = 1\n", None, {"expected_matches": 0})
        r = case_runner.run_case(d)
        self.assertFalse(r.passed)
        self.assertIn("Missing file(s): query.query", r.messages[0])

    def test_missing_folder(self):
        r = case_runner.run_case(os.path.join(self.root, "nope"))
        self.assertFalse(r.passed)
        self.assertIn("not found", r.messages[0])

    def test_invalid_expected_json(self):
        d = make_case(self.root, "j", "x = 1\n", "Call", raw_expected="{oops")
        r = case_runner.run_case(d)
        self.assertFalse(r.passed)
        self.assertIn("Invalid expected.json", r.messages[0])
        d2 = make_case(self.root, "k", "x = 1\n", "Call", {"expected_matches": "two"})
        self.assertIn("must be an integer", case_runner.run_case(d2).messages[0])
        d3 = make_case(self.root, "l", "x = 1\n", "Call", {"expected_error": "bogus"})
        self.assertFalse(case_runner.run_case(d3).passed)


class TestSuiteAndTemplates(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_discovery_and_suite_report(self):
        make_case(self.root, "b_pass", "f()\n", "Call", {"expected_matches": 1})
        make_case(self.root, "a_fail", "f()\n", "Call", {"expected_matches": 5})
        _write(os.path.join(self.root, "stray.txt"), "x")
        cases = case_runner.discover_cases(self.root)
        self.assertEqual([os.path.basename(c) for c in cases], ["a_fail", "b_pass"])
        results = [case_runner.run_case(c) for c in cases]
        text = case_runner.format_suite(results)
        self.assertIn("[FAIL] a_fail", text)
        self.assertIn("[PASS] b_pass", text)
        self.assertIn("2 tests", text)
        self.assertIn("1 passed", text)
        self.assertIn("1 failed", text)

    def test_create_case_makes_a_passing_template(self):
        path = case_runner.create_case("my_test", self.root)
        for f in ("input.py", "query.query", "expected.json"):
            self.assertTrue(os.path.isfile(os.path.join(path, f)))
        self.assertTrue(case_runner.run_case(path).passed)

    def test_create_case_refuses_duplicates_and_bad_names(self):
        case_runner.create_case("dup", self.root)
        with self.assertRaises(FileExistsError):
            case_runner.create_case("dup", self.root)
        for bad in ("", "a/b", "../x", "has space"):
            with self.assertRaises(ValueError):
                case_runner.create_case(bad, self.root)

    def test_user_case_needs_no_engine_changes(self):
        make_case(self.root, "mine", "while True:\n    pass\n",
                  "While(test.value == True)", {"expected_matches": 1})
        self.assertTrue(case_runner.run_case(os.path.join(self.root, "mine")).passed)


class TestShippedCases(unittest.TestCase):
    def test_all_shipped_cases_pass(self):
        root = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "test_cases")
        cases = case_runner.discover_cases(root)
        self.assertGreaterEqual(len(cases), 15)
        for c in cases:
            r = case_runner.run_case(c)
            self.assertTrue(r.passed, f"{r.name}: {r.messages}")


if __name__ == "__main__":
    unittest.main()
