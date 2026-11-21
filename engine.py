"""The whole pipeline in one place.

    source text --lexer--> tokens --parser--> source AST ----------------+
                                                                          v
    query text --lexer--> tokens --parser--> query AST --semantic--> QueryEvaluator --> matches
"""
import os
from dataclasses import dataclass, field

from evaluator.evaluator import QueryEvaluator
from query_language.parser import parse_query
from query_language.query_ast import format_query
from query_language.semantic import analyze
from source_parser.lexer import normalize_source
from source_parser.parser import parse_source


def read_text(path):
    """Read a UTF-8 file (a leading BOM, common on Windows, is tolerated)."""
    with open(path, encoding="utf-8-sig") as f:
        return f.read()


@dataclass
class QueryResult:
    file: str
    query: str
    matches: list = field(default_factory=list)

    def to_dict(self):
        return {"query": self.query, "file": self.file,
                "matches": [m.to_dict() for m in self.matches]}


def compile_query(query_text):
    """Query text -> validated Query AST (lexing, parsing, semantic analysis)."""
    return analyze(parse_query(query_text))


def run_query(source_text, query_text, filename="<input>"):
    """Run the full pipeline. Raises SourceError / QueryError / QuerySemanticError."""
    source = normalize_source(source_text)
    program = parse_source(source)
    query = compile_query(query_text)
    matches = QueryEvaluator(program, source).evaluate(query)
    return QueryResult(file=filename, query=format_query(query), matches=matches)


def list_query_files(directory):
    if not os.path.isdir(directory):
        return []
    return sorted(os.path.join(directory, n) for n in os.listdir(directory)
                  if n.endswith(".query"))
