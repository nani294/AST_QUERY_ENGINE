"""Command-line behaviour (runs main.py in-process)."""
import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest

import main as cli

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLE1 = os.path.join(ROOT, "examples", "sample1.py")


def run(*args):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = cli.main(list(args))
    return code, out.getvalue()


class TestCli(unittest.TestCase):
    def test_direct_query(self):
        code, out = run("--file", SAMPLE1, "--query", "Call(func.name == 'eval')")
        self.assertEqual(code, 0)
        self.assertIn("Snippet: eval(user_input)", out)
        self.assertIn("Node Type: Call", out)
        self.assertIn('Query: Call(func.name == "eval")', out)
        self.assertIn("Bindings: {}", out)

    def test_query_file_and_user_created_query(self):
        with tempfile.TemporaryDirectory() as tmp:
            qf = os.path.join(tmp, "my_query.query")
            with open(qf, "w") as f:
                f.write('# my own query\nCall(func.name == "print")\n')
            code, out = run("--file", SAMPLE1, "--query-file", qf)
        self.assertEqual(code, 0)
        self.assertIn("Snippet: print(x)", out)

    def test_json_output(self):
        code, out = run("--file", SAMPLE1, "--query", 'Call(func.name == "eval")', "--json")
        data = json.loads(out)
        self.assertEqual(data["matches"][0]["line"], 8)
        self.assertEqual(data["matches"][0]["bindings"], {})

    def test_errors_are_friendly_and_nonzero(self):
        code, out = run("--file", SAMPLE1, "--query", "UnknownNode")
        self.assertEqual(code, 1)
        self.assertIn("Semantic Error:", out)
        code, out = run("--file", SAMPLE1, "--query", "Call(")
        self.assertEqual(code, 1)
        self.assertIn("Query Error", out)
        code, out = run("--file", os.path.join(ROOT, "nope.py"), "--query", "Call")
        self.assertEqual(code, 1)
        self.assertIn("Cannot read", out)

    def test_bad_source_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = os.path.join(tmp, "bad.py")
            with open(f, "w") as fh:
                fh.write("x = (\n")
            code, out = run("--file", f, "--query", "Call")
        self.assertEqual(code, 1)
        self.assertIn("Syntax Error", out)

    def test_library_mode(self):
        code, out = run("--file", SAMPLE1, "--library")
        self.assertEqual(code, 0)
        self.assertIn("eval.query", out)

    def test_debug_commands(self):
        self.assertEqual(run("--tokens", SAMPLE1)[0], 0)
        self.assertIn("INDENT", run("--tokens", SAMPLE1)[1])
        self.assertIn("FunctionDef", run("--ast", SAMPLE1)[1])
        self.assertIn("IDENTIFIER", run("--query-tokens", "Call")[1])
        self.assertIn("NodeMatch(Call)", run("--query-ast", "Call")[1])

    def test_test_all_and_single_test(self):
        code, out = run("--test-all")
        self.assertEqual(code, 0, out)
        self.assertIn("0 failed", out)
        code, out = run("--test", os.path.join(ROOT, "test_cases", "eval_detection"))
        self.assertEqual(code, 0)
        self.assertIn("TEST PASSED", out)

    def test_create_test_then_run_it(self):
        name = "tmp_cli_created_case"
        path = os.path.join(ROOT, "test_cases", name)
        try:
            code, out = run("--create-test", name)
            self.assertEqual(code, 0)
            code, out = run("--test", path)
            self.assertEqual(code, 0)
            self.assertIn("TEST PASSED", out)
            self.assertEqual(run("--create-test", name)[0], 1)    # already exists
        finally:
            shutil.rmtree(path, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
