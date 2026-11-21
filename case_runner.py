"""User-defined test cases: a folder with input.py, query.query, expected.json.

expected.json keys (all optional except one of the first two):
    "expected_matches": 2                  number of matches
    "expected_error":   "source" | "query" | "semantic"     this stage must fail
    "expected_lines":   [3, 7]             exact start lines of the matches
    "expected_bindings": [{"$X": "open"}]  bindings of each match, in order
"""
import json
import os
import re
from dataclasses import dataclass, field

from engine import read_text
from evaluator.evaluator import QueryEvaluator
from query_language.errors import QueryError, QuerySemanticError
from query_language.parser import parse_query
from query_language.semantic import analyze
from source_parser.errors import SourceError
from source_parser.lexer import normalize_source
from source_parser.parser import parse_source

STAGES = ("Source parsing", "Query parsing", "Semantic validation", "Evaluation")
INPUT, QUERY, EXPECTED = "input.py", "query.query", "expected.json"
ERROR_STAGE = {"source": "Source parsing", "query": "Query parsing",
               "semantic": "Semantic validation"}


@dataclass
class CaseResult:
    name: str
    passed: bool = False
    stages: dict = field(default_factory=lambda: {s: 'SKIPPED' for s in STAGES})
    expected: object = None
    actual: object = None
    messages: list = field(default_factory=list)    # extra detail lines

    def format(self):
        lines = ["Running test:", self.name, ""]
        for stage in STAGES:
            lines.append(f"{stage}: {self.stages.get(stage, 'SKIPPED')}")
        if self.expected is not None:
            lines.append(f"Expected matches: {self.expected}")
            lines.append(f"Actual matches:   {self.actual}")
        lines.append("")
        lines.append("TEST PASSED" if self.passed else "TEST FAILED")
        if self.messages:
            lines.append("")
            lines.extend(self.messages)
        return "\n".join(lines)


def format_case(result):
    return result.format()


def discover_cases(root):
    if not os.path.isdir(root):
        return []
    return sorted(os.path.join(root, d) for d in os.listdir(root)
                  if os.path.isdir(os.path.join(root, d)) and not d.startswith("."))


def _load_expected(path, result):
    try:
        with open(path, encoding="utf-8-sig") as f:
            data = json.load(f)
    except json.JSONDecodeError as exc:
        result.messages.append(f"Invalid {EXPECTED}: {exc}")
        return None
    if not isinstance(data, dict):
        result.messages.append(f"Invalid {EXPECTED}: top level must be an object")
        return None
    if "expected_matches" not in data and "expected_error" not in data:
        result.messages.append(
            f"Invalid {EXPECTED}: needs 'expected_matches' or 'expected_error'")
        return None
    if "expected_matches" in data and (
            not isinstance(data["expected_matches"], int)
            or isinstance(data["expected_matches"], bool)):
        result.messages.append(f"Invalid {EXPECTED}: 'expected_matches' must be an integer")
        return None
    if data.get("expected_error") not in (None, *ERROR_STAGE):
        result.messages.append(
            f"Invalid {EXPECTED}: 'expected_error' must be one of {sorted(ERROR_STAGE)}")
        return None
    return data


def run_case(path):
    path = os.path.normpath(path)
    result = CaseResult(name=os.path.basename(path))
    if not os.path.isdir(path):
        result.messages.append(f"Test folder not found: {path}")
        return result
    files = {n: os.path.join(path, n) for n in (INPUT, QUERY, EXPECTED)}
    missing = [n for n, p in files.items() if not os.path.isfile(p)]
    if missing:
        result.messages.append("Missing file(s): " + ", ".join(missing))
        return result
    expected = _load_expected(files[EXPECTED], result)
    if expected is None:
        return result
    expected_error = expected.get("expected_error")

    state = {"program": None, "query": None, "source": None}

    def stage(name, action, exc_types):
        """Run one pipeline stage; returns True if it succeeded."""
        try:
            action()
        except exc_types as exc:
            result.stages[name] = "FAIL"
            if expected_error and ERROR_STAGE[expected_error] == name:
                result.passed = True
                result.messages.append("Failed as expected:")
                result.messages.append(exc.format())
            else:
                result.messages.append(exc.format())
            return False
        result.stages[name] = "PASS"
        return True

    def parse_src():
        state["source"] = normalize_source(read_text(files[INPUT]))
        state["program"] = parse_source(state["source"])

    def parse_q():
        state["query"] = parse_query(read_text(files[QUERY]))

    if not stage("Source parsing", parse_src, SourceError):
        return result
    if not stage("Query parsing", parse_q, QueryError):
        return result
    if not stage("Semantic validation", lambda: analyze(state["query"]), QuerySemanticError):
        return result

    matches = QueryEvaluator(state["program"], state["source"]).evaluate(state["query"])
    result.stages["Evaluation"] = "PASS"
    if expected_error:
        result.messages.append(f"Expected a {expected_error} error, but the pipeline succeeded")
        return result
    result.expected = expected["expected_matches"]
    result.actual = len(matches)
    ok = result.expected == result.actual
    if "expected_lines" in expected:
        lines = [m.line for m in matches]
        if lines != expected["expected_lines"]:
            ok = False
            result.messages.append(
                f"Expected match lines {expected['expected_lines']}, got {lines}")
    if "expected_bindings" in expected:
        got = [m.bindings for m in matches]
        if got != expected["expected_bindings"]:
            ok = False
            result.messages.append(
                f"Expected bindings {expected['expected_bindings']}, got {got}")
    result.passed = ok
    return result


def run_all(root):
    return [run_case(p) for p in discover_cases(root)]


def format_suite(results):
    bar = "=" * 32
    lines = [bar, "AST Query Engine Test Suite", bar, ""]
    for r in results:
        lines.append(f"[{'PASS' if r.passed else 'FAIL'}] {r.name}")
    passed = sum(r.passed for r in results)
    lines += ["", "-" * 32, f"{len(results)} tests", f"{passed} passed",
              f"{len(results) - passed} failed", "-" * 32]
    for r in results:
        if not r.passed:
            lines += ["", r.format()]
    return "\n".join(lines)


_TEMPLATES = {
    INPUT: 'def greet(name):\n    print("hello", name)\n    return name\n',
    QUERY: '# Find every call to print()\nCall(func.name == "print")\n',
    EXPECTED: '{\n    "expected_matches": 1\n}\n',
}


def create_case(name, root):
    if not re.fullmatch(r"[A-Za-z0-9_\-]+", name):
        raise ValueError("Test name may only contain letters, digits, '_' and '-'")
    path = os.path.join(root, name)
    if os.path.exists(path):
        raise FileExistsError(f"Test case already exists: {path}")
    os.makedirs(path)
    for fname, text in _TEMPLATES.items():
        with open(os.path.join(path, fname), "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
    return path
