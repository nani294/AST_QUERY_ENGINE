# AST Query Engine (Mini CodeQL / Semgrep)

Search source code by **structure**, not text. Two languages, two lexers, two
parsers (all SLY) - no use of Python's `ast` module anywhere.

```
Source (.py) -> SLY lexer -> INDENT/DEDENT layout -> SLY parser -> custom AST --------+
Query text   -> SLY lexer -> SLY parser -> Query AST -> semantic analyzer ------------+-> evaluator -> text / JSON
```

| Compiler stage        | Where                                              |
|-----------------------|----------------------------------------------------|
| Lexical analysis      | `source_parser/lexer.py`, `query_language/lexer.py`|
| Layout (INDENT/DEDENT)| `source_parser/indentation.py`                     |
| Syntax analysis       | `source_parser/parser.py`, `query_language/parser.py` |
| AST construction      | `source_parser/ast_nodes.py`, `query_language/query_ast.py` |
| Semantic analysis     | `query_language/semantic.py`                       |
| Traversal             | `evaluator/traversal.py`                           |
| Evaluation            | `evaluator/evaluator.py`, `evaluator/matcher.py`   |
| Pipeline / reporting  | `engine.py`, `reporting.py`                        |
| User test cases       | `case_runner.py`                                   |

## Install

```
pip install -r requirements.txt
python main.py --check
```

## Use

```
python main.py --file examples/sample1.py --query "Call(func.name == 'eval')"
python main.py --file examples/sample1.py --query-file queries/eval.query --json
python main.py --file examples/sample2.py --library          # run all queries in queries/
python main.py --test test_cases/open_without_with
python main.py --test-all
python main.py --create-test my_test
```

Debug views: `--tokens FILE [--raw]`, `--ast FILE`, `--query-tokens "Q"`, `--query-ast "Q"`.

Columns in reports are 1-based (like an editor); AST `col_offset` is 0-based.

## Query language

```
Call                                   every Call node
Call(func.name == "open")              attribute predicate (== != < > <= >=)
FunctionDef(num_params > 5)            computed attributes
Call(func.name == $X)                  metavariable: binds $X, must stay equal
parent(For)  ancestor(With)  descendant(For)        relationships
FunctionDef descendant For             infix form  (= FunctionDef AND descendant(For))
A AND B   A OR B   NOT A   ( ... )     precedence: NOT > AND > OR
Call(func.name == "a" OR func.name == "b", num_args > 1)   comma = AND inside ( )
```
Queries may span lines and contain `# comments`.

Node types: Program FunctionDef Parameter Assign If For While With WithItem
Return Try ExceptHandler Import Alias Pass Break Continue Name Constant Call
Keyword Attribute Subscript BinaryOp UnaryOp Compare BoolOp Tuple List.
Attributes per type are listed by the semantic error when you mistype one.
`elif` is an `If` inside `orelse` with `is_elif == True`. Expression statements
are stored directly in a body (there is no `Expr` wrapper).

## Source language subset

def, assignment (incl. tuple targets), if/elif/else, for, while, with, try/except/finally,
return, import / from-import, pass/break/continue, one-line bodies (`if x: pass`),
calls (positional + keyword), attributes, subscripts, + - * / %, comparisons
(== != < > <= >= in, not in, is, is not), and/or/not, list and tuple literals,
strings (incl. triple-quoted), numbers, True/False/None, comments, line continuation.
Not supported: classes, lambda, comprehensions, decorators, f-strings, `**`, `//`,
augmented assignment (`+=`), dict/set literals, `try/else`.

## Your own queries and tests

Write `my.query`, then `python main.py --file X.py --query-file my.query`.

`python main.py --create-test NAME` makes `test_cases/NAME/{input.py,query.query,expected.json}`.
`expected.json`: `{"expected_matches": 1}` plus optional `"expected_lines": [..]`,
`"expected_bindings": [{..}]`, or `"expected_error": "source" | "query" | "semantic"`.

## Web interface

```
python server.py            # or: python main.py --serve
```

Then open <http://127.0.0.1:8000> (a browser tab opens automatically; add `--no-browser`
to stop that, or `--port 8001` if port 8000 is busy). Stop it with Ctrl+C.

1. **Source code**: upload a `.py` file, drag one onto the box, pick an example, or type.
2. **Query**: upload a `.query` file, pick a ready-made query, or type your own.
3. **Run query** (or Ctrl+Enter). Matches appear as cards; click one to highlight the exact
   code in the source view. Metavariable bindings are shown as chips. Download or copy the JSON.

Other tabs: *Scan with all ready-made queries* (a count per query), *Compiler stages*
(tokens, AST, Query AST: handy for explaining the project), and *Test case* (upload
`input.py`, `query.query`, `expected.json` and get PASS/FAIL).

The server uses only the Python standard library, listens on this computer only
(127.0.0.1), and only *parses* the uploaded code, it never runs it.

## Automated tests

```
python -m unittest discover -s tests -t . -v
```
