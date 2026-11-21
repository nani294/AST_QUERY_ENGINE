"""Every ready-made query must parse, validate and execute for real."""
import os
import unittest

from engine import read_text, run_query

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QDIR = os.path.join(ROOT, "queries")
EDIR = os.path.join(ROOT, "examples")


def lines(example, query_name):
    src = read_text(os.path.join(EDIR, example))
    q = read_text(os.path.join(QDIR, query_name + ".query"))
    return [m.line for m in run_query(src, q, example).matches]


class TestLibrary(unittest.TestCase):
    def test_at_least_15_queries(self):
        self.assertGreaterEqual(len([f for f in os.listdir(QDIR) if f.endswith(".query")]), 15)

    def test_every_query_runs_on_every_example(self):
        examples = [f for f in os.listdir(EDIR) if f.endswith(".py")]
        self.assertGreaterEqual(len(examples), 2)
        for q in sorted(os.listdir(QDIR)):
            if not q.endswith(".query"):
                continue
            qtext = read_text(os.path.join(QDIR, q))
            for e in examples:
                run_query(read_text(os.path.join(EDIR, e)), qtext, e)   # must not raise

    def test_known_results_on_sample1(self):
        self.assertEqual(lines("sample1.py", "eval"), [8])
        self.assertEqual(lines("sample1.py", "open_without_with"), [2])
        self.assertEqual(lines("sample1.py", "nested_for"), [4])
        self.assertEqual(lines("sample1.py", "bare_except"), [12])
        self.assertEqual(lines("sample1.py", "function_with_for"), [1])
        self.assertEqual(lines("sample1.py", "function_with_while"), [])
        self.assertEqual(lines("sample1.py", "print_calls"), [6])

    # Line numbers below were derived by reading examples/sample2.py by hand.
    def test_known_results_on_sample2(self):
        self.assertEqual(lines("sample2.py", "exec"), [19])
        self.assertEqual(lines("sample2.py", "while_true"), [17])
        self.assertEqual(lines("sample2.py", "open_without_with"), [10])
        self.assertEqual(lines("sample2.py", "deeply_nested_if"), [24])
        self.assertEqual(lines("sample2.py", "multiple_returns"), [16])
        self.assertEqual(lines("sample2.py", "many_parameters"), [])
        self.assertEqual(lines("sample2.py", "deep_function"), [16])
        self.assertEqual(lines("sample2.py", "function_with_for_and_while"), [])
        self.assertEqual(lines("sample2.py", "hardcoded_password"), [5])
        self.assertEqual(lines("sample2.py", "dangerous_imports"), [2, 3])
        self.assertEqual(lines("sample2.py", "dangerous_calls"), [19, 33])
        self.assertEqual(lines("sample2.py", "nested_for"), [30])
        self.assertEqual(lines("sample2.py", "large_function"), [])

    def test_sample3_exercises_wide_syntax(self):
        self.assertEqual(lines("sample3.py", "print_calls"), [17, 19])
        self.assertEqual(lines("sample3.py", "function_with_for"), [2])
        self.assertEqual(lines("sample3.py", "nested_loops"), [])
        self.assertEqual(lines("sample3.py", "bare_except"), [])


if __name__ == "__main__":
    unittest.main()
