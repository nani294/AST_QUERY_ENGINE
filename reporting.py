"""Turn a QueryResult into human-readable text or JSON."""
import json


def _short(snippet):
    first, *rest = snippet.split("\n")
    return first + (f" ... (+{len(rest)} more lines)" if rest else "")


def format_text(result):
    if not result.matches:
        return "No matches found."
    blocks = []
    for m in result.matches:
        blocks.append("\n".join([
            f"File: {result.file}",
            f"Line: {m.line}",
            f"Column: {m.column}",
            f"Node Type: {m.node_type}",
            f"Snippet: {_short(m.snippet)}",
            f"Query: {result.query}",
            f"Bindings: {json.dumps(m.bindings, ensure_ascii=False)}",
        ]))
    n = len(result.matches)
    return "\n\n".join(blocks) + f"\n\n{n} match{'es' if n != 1 else ''} found."


def format_json(result):
    return json.dumps(result.to_dict(), indent=4, ensure_ascii=False)
