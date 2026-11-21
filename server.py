"""Web interface for the AST Query Engine (standard library only).

    python server.py                 # then open http://127.0.0.1:8000
    python main.py --serve

The browser reads the uploaded files and sends their TEXT to this server as
JSON. The server runs the normal pipeline (lexer -> parser -> semantic
analysis -> evaluator) and sends the result back. Nothing leaves your machine:
the server listens on 127.0.0.1 only, and it never executes the code it
analyzes - it only parses it.

API
    GET  /                 the web page (web/index.html)
    GET  /api/queries      the ready-made queries in queries/
    GET  /api/examples     the sample sources in examples/
    POST /api/run          {source, query, filename}   -> matches or an error
    POST /api/inspect      {source, query}             -> tokens / ASTs
    POST /api/library      {source, filename}          -> counts for every ready-made query
    POST /api/case         {input, query, expected}    -> PASS / FAIL for a test case
"""
import argparse
import json
import os
import re
import sys
import tempfile
import threading
import time
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from case_runner import STAGES, run_case                                  # noqa: E402
from engine import compile_query, list_query_files, read_text, run_query  # noqa: E402
from evaluator.evaluator import QueryEvaluator                            # noqa: E402
from query_language.errors import QueryError, QuerySemanticError          # noqa: E402
from query_language.lexer import dump_query_tokens, tokenize_query        # noqa: E402
from query_language.parser import parse_query                             # noqa: E402
from query_language.query_ast import dump_query, format_query             # noqa: E402
from query_language.semantic import analyze                               # noqa: E402
from source_parser.ast_nodes import dump                                  # noqa: E402
from source_parser.errors import SourceError                              # noqa: E402
from source_parser.lexer import (dump_tokens, normalize_source,           # noqa: E402
                                 raw_tokens, tokenize)
from source_parser.parser import parse_source                             # noqa: E402

WEB_DIR = os.path.join(ROOT, "web")
QUERY_DIR = os.path.join(ROOT, "queries")
EXAMPLE_DIR = os.path.join(ROOT, "examples")
MAX_BODY = 2 * 1024 * 1024          # 2 MB per request is plenty for source files
DRAIN_LIMIT = 64 * 1024 * 1024      # bigger bodies are not even read

ANALYSIS_ERRORS = (SourceError, QueryError, QuerySemanticError)


class ApiError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


# ------------------------------------------------------------------ helpers
def _text(payload, key, required=True):
    value = payload.get(key)
    if value is None and not required:
        return ""
    if not isinstance(value, str):
        raise ApiError(400, f"Field '{key}' must be a string")
    return value.lstrip("\ufeff")        # a UTF-8 BOM would confuse the lexer


def _filename(payload):
    name = re.split(r"[\\/]", str(payload.get("filename") or ""))[-1]   # keep only the file name
    return name or "<input>"


def _stage_of(exc):
    if isinstance(exc, SourceError):
        return "source"
    if isinstance(exc, QuerySemanticError):
        return "semantic"
    return "query"


def error_response(exc):
    """Describe a SourceError / QueryError / QuerySemanticError for the browser."""
    stage = _stage_of(exc)
    resp = {"ok": False, "stage": stage,
            "where": "source" if stage == "source" else "query",
            "message": exc.format(), "line": None, "column": None}
    if stage == "semantic":
        resp["issues"] = [{"message": i.message, "hint": i.hint,
                           "line": i.lineno,
                           "column": None if i.column is None else i.column + 1}
                          for i in exc.issues]
        first = exc.issues[0] if exc.issues else None
        if first is not None:
            resp["line"] = first.lineno
            resp["column"] = None if first.column is None else first.column + 1
    else:
        resp["line"] = exc.lineno
        resp["column"] = None if exc.column is None else exc.column + 1
    return resp


def _description(query_text):
    for line in query_text.splitlines():
        line = line.strip()
        if line.startswith("#"):
            return line.lstrip("#").strip()
    return ""


# ---------------------------------------------------------------- endpoints
def api_run(payload):
    source = _text(payload, "source")
    query = _text(payload, "query")
    filename = _filename(payload)
    start = time.perf_counter()
    try:
        result = run_query(source, query, filename)
    except ANALYSIS_ERRORS as exc:
        return error_response(exc)
    return {"ok": True, "file": filename, "query": result.query,
            "count": len(result.matches),
            "matches": [m.to_dict() for m in result.matches],
            "elapsed_ms": round((time.perf_counter() - start) * 1000, 1)}


def api_inspect(payload):
    """The intermediate results of every compiler stage (for learning/debugging)."""
    source = normalize_source(_text(payload, "source"))
    query = _text(payload, "query", required=False)
    out = {"ok": True, "raw_tokens": None, "tokens": None, "ast": None,
           "source_error": None, "query_tokens": None, "query_ast": None,
           "canonical": None, "query_error": None, "semantic_error": None}
    try:
        out["raw_tokens"] = dump_tokens(raw_tokens(source))
        out["tokens"] = dump_tokens(tokenize(source))
        out["ast"] = dump(parse_source(source))
    except SourceError as exc:
        out["source_error"] = exc.format()
    if query.strip():
        try:
            out["query_tokens"] = dump_query_tokens(tokenize_query(query))
            tree = parse_query(query)
            out["query_ast"] = dump_query(tree)
            out["canonical"] = format_query(tree)
            analyze(tree)
        except QuerySemanticError as exc:
            out["semantic_error"] = exc.format()
        except QueryError as exc:
            out["query_error"] = exc.format()
    return out


def api_library(payload):
    """Run every ready-made query on one source file."""
    source = normalize_source(_text(payload, "source"))
    try:
        program = parse_source(source)
    except SourceError as exc:
        return error_response(exc)
    evaluator = QueryEvaluator(program, source)
    rows = []
    for path in list_query_files(QUERY_DIR):
        text = read_text(path)
        row = {"name": os.path.basename(path)[:-len(".query")],
               "description": _description(text), "query": text}
        try:
            matches = evaluator.evaluate(compile_query(text))
            row["count"] = len(matches)
            row["lines"] = [m.line for m in matches][:50]
        except (QueryError, QuerySemanticError) as exc:
            row["error"] = exc.format()
        rows.append(row)
    return {"ok": True, "file": _filename(payload), "rows": rows}


def api_case(payload):
    """Run a user-made test case (input.py + query.query + expected.json)."""
    files = {"input.py": _text(payload, "input"),
             "query.query": _text(payload, "query"),
             "expected.json": _text(payload, "expected")}
    name = str(payload.get("name") or "")
    if not re.fullmatch(r"[A-Za-z0-9_\-]{1,60}", name):
        name = "uploaded_test"
    with tempfile.TemporaryDirectory() as tmp:
        case_dir = os.path.join(tmp, name)
        os.makedirs(case_dir)
        for fname, text in files.items():
            with open(os.path.join(case_dir, fname), "w",
                      encoding="utf-8", newline="\n") as f:
                f.write(text)
        result = run_case(case_dir)
    return {"ok": True, "name": result.name, "passed": result.passed,
            "stages": [{"name": s, "status": result.stages.get(s, "SKIPPED")}
                       for s in STAGES],
            "expected": result.expected, "actual": result.actual,
            "messages": result.messages, "report": result.format()}


def api_queries():
    rows = []
    for path in list_query_files(QUERY_DIR):
        text = read_text(path)
        rows.append({"name": os.path.basename(path)[:-len(".query")],
                     "description": _description(text), "query": text})
    return {"ok": True, "queries": rows}


def api_examples():
    rows = []
    if os.path.isdir(EXAMPLE_DIR):
        for name in sorted(os.listdir(EXAMPLE_DIR)):
            if name.endswith(".py"):
                rows.append({"name": name,
                             "source": read_text(os.path.join(EXAMPLE_DIR, name))})
    return {"ok": True, "examples": rows}


GET_ROUTES = {"/api/queries": api_queries, "/api/examples": api_examples,
              "/api/health": lambda: {"ok": True}}
POST_ROUTES = {"/api/run": api_run, "/api/inspect": api_inspect,
               "/api/library": api_library, "/api/case": api_case}


# ------------------------------------------------------------------- server
class Handler(BaseHTTPRequestHandler):
    server_version = "ASTQueryEngine/1.0"

    def log_message(self, fmt, *args):
        sys.stderr.write("  %s - %s\n" % (self.address_string(), fmt % args))

    def _send(self, status, body, content_type):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8")

    def _fail(self, status, message, stage="input"):
        self._json(status, {"ok": False, "stage": stage, "where": "source",
                            "message": message, "line": None, "column": None})

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            try:
                with open(os.path.join(WEB_DIR, "index.html"), "rb") as f:
                    self._send(200, f.read(), "text/html; charset=utf-8")
            except OSError:
                self._fail(500, "web/index.html is missing", "internal")
            return
        route = GET_ROUTES.get(path)
        if route is None:
            self._fail(404, f"Not found: {path}")
            return
        self._call(route)

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        route = POST_ROUTES.get(path)
        if route is None:
            self._fail(404, f"Not found: {path}")
            return
        try:
            length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            self._fail(411, "Content-Length header is required")
            return
        if length < 0 or length > MAX_BODY:
            # Read (and throw away) the body so the browser sees our message
            # instead of a dropped connection; refuse absurd sizes outright.
            if 0 <= length <= DRAIN_LIMIT:
                remaining = length
                while remaining > 0:
                    chunk = self.rfile.read(min(65536, remaining))
                    if not chunk:
                        break
                    remaining -= len(chunk)
            else:
                self.close_connection = True
            self._fail(413, f"Request too large (limit {MAX_BODY // 1024} KB)")
            return
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("top level must be an object")
        except (ValueError, UnicodeDecodeError) as exc:
            self._fail(400, f"Request body is not valid JSON: {exc}")
            return
        self._call(route, payload)

    def _call(self, route, *args):
        try:
            self._json(200, route(*args))
        except ApiError as exc:
            self._fail(exc.status, exc.message)
        except Exception as exc:                       # a bug in the engine
            traceback.print_exc()
            self._fail(500, f"Internal error: {type(exc).__name__}: {exc}", "internal")


def make_server(host="127.0.0.1", port=8000):
    return ThreadingHTTPServer((host, port), Handler)


def serve(host="127.0.0.1", port=8000, open_browser=True):
    try:
        httpd = make_server(host, port)
    except OSError as exc:
        print(f"Cannot start the server on {host}:{port}: {exc}")
        print(f"Try another port:  python server.py --port {port + 1}")
        return 1
    url = f"http://{host}:{httpd.server_address[1]}/"
    print("AST Query Engine - web interface")
    print(f"  Open {url} in your browser   (press Ctrl+C to stop)")
    if open_browser:
        threading.Timer(0.6, webbrowser.open, [url]).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        httpd.server_close()
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Web interface for the AST Query Engine")
    ap.add_argument("--host", default="127.0.0.1",
                    help="address to listen on (default 127.0.0.1 = this computer only)")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--no-browser", action="store_true",
                    help="do not open the browser automatically")
    args = ap.parse_args(argv)
    return serve(args.host, args.port, not args.no_browser)


if __name__ == "__main__":
    sys.exit(main())
