"""Tests for the web interface: the JSON API, run over real HTTP on a free port."""
import json
import threading
import unittest
import urllib.error
import urllib.request

import server

SOURCE = 'def f(x):\n    g = open(x)\n    with open("a") as h:\n        pass\n    return eval(x)\n'
OPEN_NOT_IN_WITH = 'Call(func.name == "open") AND NOT ancestor(With)'


class ServerTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = server.make_server("127.0.0.1", 0)
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}"
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def get(self, path):
        with urllib.request.urlopen(self.base + path) as r:
            return r.status, r.read()

    def post(self, path, payload, raw=None):
        data = raw if raw is not None else json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(self.base + path, data=data,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())


class TestPages(ServerTestCase):
    def test_index_page_is_served(self):
        status, body = self.get("/")
        self.assertEqual(status, 200)
        self.assertIn(b"AST Query Engine", body)

    def test_unknown_path_is_404(self):
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self.get("/nope")
        self.assertEqual(cm.exception.code, 404)

    def test_library_and_examples_listed(self):
        _, body = self.get("/api/queries")
        names = [q["name"] for q in json.loads(body)["queries"]]
        self.assertGreaterEqual(len(names), 15)
        self.assertIn("eval", names)
        _, body = self.get("/api/examples")
        self.assertIn("sample1.py", [e["name"] for e in json.loads(body)["examples"]])


class TestRun(ServerTestCase):
    def test_run_returns_matches(self):
        status, r = self.post("/api/run", {"source": SOURCE, "query": OPEN_NOT_IN_WITH,
                                           "filename": "demo.py"})
        self.assertEqual(status, 200)
        self.assertTrue(r["ok"])
        self.assertEqual(r["count"], 1)
        m = r["matches"][0]
        self.assertEqual((m["node_type"], m["line"], m["column"]), ("Call", 2, 9))
        self.assertEqual(m["snippet"], "open(x)")
        self.assertEqual(r["file"], "demo.py")
        self.assertEqual(r["query"], OPEN_NOT_IN_WITH)

    def test_metavariable_bindings_are_returned(self):
        _, r = self.post("/api/run", {"source": SOURCE, "query": "Call(func.name == $X)"})
        self.assertEqual([m["bindings"]["$X"] for m in r["matches"]],
                         ["open", "open", "eval"])

    def test_filename_path_is_reduced_to_a_name(self):
        _, r = self.post("/api/run", {"source": "x = 1\n", "query": "Name",
                                      "filename": "C:\\secret\\dir\\a.py"})
        self.assertNotIn("secret", r["file"])

    def test_bom_and_windows_line_endings(self):
        src = "\ufeffdef f():\r\n    eval(x)\r\n"
        _, r = self.post("/api/run", {"source": src, "query": 'Call(func.name == "eval")'})
        self.assertTrue(r["ok"])
        self.assertEqual(r["matches"][0]["line"], 2)

    def test_source_syntax_error(self):
        _, r = self.post("/api/run", {"source": "def f(:\n  pass\n", "query": "Call"})
        self.assertFalse(r["ok"])
        self.assertEqual((r["stage"], r["where"], r["line"]), ("source", "source", 1))
        self.assertIn("Syntax Error", r["message"])

    def test_query_syntax_error(self):
        _, r = self.post("/api/run", {"source": SOURCE, "query": 'Call(func.name == "x" AND'})
        self.assertEqual((r["ok"], r["stage"], r["where"]), (False, "query", "query"))
        self.assertIn("Query Error", r["message"])

    def test_semantic_error_lists_issues(self):
        _, r = self.post("/api/run", {"source": SOURCE, "query": "UnknownNode"})
        self.assertEqual(r["stage"], "semantic")
        self.assertIn("Unknown AST node type 'UnknownNode'", r["issues"][0]["message"])
        self.assertEqual(r["line"], 1)

    def test_empty_query_is_a_query_error(self):
        _, r = self.post("/api/run", {"source": SOURCE, "query": "   "})
        self.assertEqual(r["stage"], "query")

    def test_empty_source_is_fine(self):
        _, r = self.post("/api/run", {"source": "", "query": "Call"})
        self.assertTrue(r["ok"])
        self.assertEqual(r["count"], 0)


class TestBadRequests(ServerTestCase):
    def test_missing_field(self):
        status, r = self.post("/api/run", {"query": "Call"})
        self.assertEqual(status, 400)
        self.assertFalse(r["ok"])

    def test_wrong_type(self):
        status, _ = self.post("/api/run", {"source": 5, "query": "Call"})
        self.assertEqual(status, 400)

    def test_invalid_json(self):
        status, r = self.post("/api/run", None, raw=b"{not json")
        self.assertEqual(status, 400)
        self.assertIn("JSON", r["message"])

    def test_body_must_be_an_object(self):
        status, _ = self.post("/api/run", None, raw=b"[1, 2]")
        self.assertEqual(status, 400)

    def test_oversized_body_rejected(self):
        status, _ = self.post("/api/run", {"source": "x" * (server.MAX_BODY + 10), "query": "Call"})
        self.assertEqual(status, 413)

    def test_unknown_post_path(self):
        status, _ = self.post("/api/unknown", {})
        self.assertEqual(status, 404)


class TestOtherEndpoints(ServerTestCase):
    def test_library_scan(self):
        _, r = self.post("/api/library", {"source": SOURCE})
        self.assertTrue(r["ok"])
        rows = {row["name"]: row for row in r["rows"]}
        self.assertEqual(rows["eval"]["count"], 1)
        self.assertEqual(rows["open_without_with"]["count"], 1)
        self.assertEqual(rows["open_without_with"]["lines"], [2])
        self.assertTrue(all("error" not in row for row in rows.values()))

    def test_library_scan_reports_source_error(self):
        _, r = self.post("/api/library", {"source": "def (:"})
        self.assertFalse(r["ok"])
        self.assertEqual(r["stage"], "source")

    def test_inspect_shows_every_stage(self):
        _, r = self.post("/api/inspect", {"source": SOURCE, "query": OPEN_NOT_IN_WITH})
        self.assertIn("INDENT", r["tokens"])
        self.assertNotIn("INDENT", r["raw_tokens"])
        self.assertIn("FunctionDef", r["ast"])
        self.assertIn("ANCESTOR", r["query_tokens"])
        self.assertIn("NodeMatch(Call)", r["query_ast"])
        self.assertEqual(r["canonical"], OPEN_NOT_IN_WITH)
        for key in ("source_error", "query_error", "semantic_error"):
            self.assertIsNone(r[key])

    def test_inspect_keeps_partial_results_on_errors(self):
        _, r = self.post("/api/inspect", {"source": "x = (\n", "query": "UnknownNode"})
        self.assertIsNotNone(r["tokens"])
        self.assertIsNone(r["ast"])
        self.assertIn("Syntax Error", r["source_error"])
        self.assertIn("Semantic Error", r["semantic_error"])

    def test_case_pass_and_fail(self):
        base = {"input": SOURCE, "query": 'Call(func.name == "eval")'}
        _, ok = self.post("/api/case", dict(base, expected='{"expected_matches": 1}'))
        self.assertTrue(ok["passed"])
        self.assertEqual([s["status"] for s in ok["stages"]], ["PASS"] * 4)
        _, bad = self.post("/api/case", dict(base, expected='{"expected_matches": 2}'))
        self.assertFalse(bad["passed"])
        self.assertEqual((bad["expected"], bad["actual"]), (2, 1))

    def test_case_expected_error(self):
        _, r = self.post("/api/case", {"input": SOURCE, "query": "UnknownNode",
                                       "expected": '{"expected_error": "semantic"}'})
        self.assertTrue(r["passed"])

    def test_case_with_invalid_expected_json(self):
        _, r = self.post("/api/case", {"input": SOURCE, "query": "Call", "expected": "{oops"})
        self.assertFalse(r["passed"])
        self.assertIn("Invalid expected.json", "\n".join(r["messages"]))


if __name__ == "__main__":
    unittest.main()
