"""AST Query Engine (Mini CodeQL / Semgrep) - command line interface.

    python main.py --file examples/sample1.py --query "Call(func.name == 'eval')"
    python main.py --file examples/sample1.py --query-file queries/eval.query --json
    python main.py --test test_cases/open_without_with
    python main.py --test-all
    python main.py --create-test my_test
    python main.py --file examples/sample2.py --library
    python main.py --serve            (web interface at http://127.0.0.1:8000)
"""
import argparse
import importlib
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

DEFAULT_TEST_DIR = os.path.join(ROOT, "test_cases")
QUERY_DIR = os.path.join(ROOT, "queries")
PACKAGES = ["source_parser", "query_language", "evaluator"]


def check_environment():
    ok = True
    v = sys.version_info
    good = v >= (3, 8)
    print(f"Python version : {v.major}.{v.minor}.{v.micro}  [{'OK' if good else 'TOO OLD (need 3.8+)'}]")
    ok &= good
    try:
        import sly
        print(f"SLY            : {getattr(sly, '__version__', 'unknown')}  [OK]")
    except ImportError:
        print("SLY            : NOT INSTALLED  -> run: pip install -r requirements.txt")
        ok = False
    for name in PACKAGES:
        try:
            importlib.import_module(name)
            print(f"package {name:<15}: [OK]")
        except Exception as exc:
            print(f"package {name:<15}: FAILED ({exc})")
            ok = False
    print("\nEnvironment check:", "PASSED" if ok else "FAILED")
    return ok


def _errors():
    from query_language.errors import QueryError, QuerySemanticError
    from source_parser.errors import SourceError
    return (SourceError, QueryError, QuerySemanticError)


def cmd_tokens(path, raw):
    from engine import read_text
    from source_parser.lexer import dump_tokens, raw_tokens, tokenize
    text = read_text(path)
    print(dump_tokens(raw_tokens(text) if raw else tokenize(text)))


def cmd_ast(path):
    from engine import read_text
    from source_parser.ast_nodes import dump
    from source_parser.parser import parse_source
    print(dump(parse_source(read_text(path))))


def cmd_query_debug(text, tree):
    from query_language.lexer import dump_query_tokens, tokenize_query
    from query_language.parser import parse_query
    from query_language.query_ast import dump_query
    if tree:
        print(dump_query(parse_query(text)))
    else:
        print(dump_query_tokens(tokenize_query(text)))


def cmd_run(args):
    from engine import read_text, run_query
    from reporting import format_json, format_text
    source = read_text(args.file)
    query = args.query if args.query is not None else read_text(args.query_file)
    result = run_query(source, query, args.file)
    print(format_json(result) if args.json else format_text(result))


def cmd_library(path):
    from engine import list_query_files, read_text, run_query
    source = read_text(path)
    files = list_query_files(QUERY_DIR)
    print(f"Running {len(files)} library queries on {path}\n")
    for qf in files:
        name = os.path.basename(qf)
        try:
            n = len(run_query(source, read_text(qf), path).matches)
            print(f"{name:<36} {n:>3} match{'es' if n != 1 else ''}")
        except _errors() as exc:
            print(f"{name:<36} ERROR: {exc.message}")


def resolve_test_path(arg):
    if os.path.isdir(arg):
        return arg
    alt = os.path.join(DEFAULT_TEST_DIR, arg)
    return alt if os.path.isdir(alt) else arg


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    ap = argparse.ArgumentParser(description="AST Query Engine (Mini CodeQL / Semgrep)")
    ap.add_argument("--file", help="source file to analyze")
    q = ap.add_mutually_exclusive_group()
    q.add_argument("--query", help="query text")
    q.add_argument("--query-file", help="file containing a query")
    ap.add_argument("--json", action="store_true", help="print results as JSON")
    ap.add_argument("--test", metavar="DIR", help="run one test case folder")
    ap.add_argument("--test-all", action="store_true", help="run every test case")
    ap.add_argument("--test-dir", default=DEFAULT_TEST_DIR, help="folder used by --test-all")
    ap.add_argument("--create-test", metavar="NAME", help="create a test case template")
    ap.add_argument("--library", action="store_true",
                    help="with --file: run every query in queries/ on it")
    ap.add_argument("--tokens", metavar="FILE", help="print the tokens of a source file")
    ap.add_argument("--raw", action="store_true", help="with --tokens: before INDENT/DEDENT")
    ap.add_argument("--ast", metavar="FILE", help="print the custom AST of a source file")
    ap.add_argument("--query-tokens", metavar="QUERY", help="print the tokens of a query")
    ap.add_argument("--query-ast", metavar="QUERY", help="print the Query AST of a query")
    ap.add_argument("--check", action="store_true", help="verify the environment")
    ap.add_argument("--serve", action="store_true", help="start the web interface")
    ap.add_argument("--port", type=int, default=8000, help="port for --serve (default 8000)")
    ap.add_argument("--no-browser", action="store_true", help="with --serve: do not open a browser")
    args = ap.parse_args(argv)

    if args.check:
        return 0 if check_environment() else 1

    if args.serve:
        from server import serve
        return serve(port=args.port, open_browser=not args.no_browser)

    try:
        if args.create_test:
            from case_runner import EXPECTED, INPUT, QUERY, create_case
            path = create_case(args.create_test, DEFAULT_TEST_DIR)
            print(f"Created test case: {path}")
            print(f"  edit {INPUT}, {QUERY} and {EXPECTED}, then run:")
            print(f"  python main.py --test {os.path.relpath(path, os.getcwd())}")
            return 0
        if args.test:
            from case_runner import run_case
            result = run_case(resolve_test_path(args.test))
            print(result.format())
            return 0 if result.passed else 1
        if args.test_all:
            from case_runner import format_suite, run_all
            results = run_all(args.test_dir)
            if not results:
                print(f"No test cases found in {args.test_dir}")
                return 1
            print(format_suite(results))
            return 0 if all(r.passed for r in results) else 1
        if args.tokens:
            cmd_tokens(args.tokens, args.raw)
            return 0
        if args.ast:
            cmd_ast(args.ast)
            return 0
        if args.query_tokens is not None:
            cmd_query_debug(args.query_tokens, tree=False)
            return 0
        if args.query_ast is not None:
            cmd_query_debug(args.query_ast, tree=True)
            return 0
        if args.library:
            if not args.file:
                ap.error("--library needs --file")
            cmd_library(args.file)
            return 0
        if args.file:
            if args.query is None and not args.query_file:
                ap.error("--file needs --query or --query-file")
            cmd_run(args)
            return 0
    except _errors() as exc:
        print(exc.format())
        return 1
    except FileExistsError as exc:
        print(f"Error: {exc}")
        return 1
    except OSError as exc:
        print(f"Cannot read file: {exc}")
        return 1
    except ValueError as exc:
        print(f"Error: {exc}")
        return 1

    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
