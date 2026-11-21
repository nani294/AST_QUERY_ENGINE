"""Low-level matching helpers: attribute paths, comparisons, snippets, results."""
from dataclasses import dataclass, field

from source_parser.ast_nodes import ASTNode, attribute_kind


def resolve_path(node, path):
    """Follow e.g. ['func', 'name'] from `node`. Returns (found, value).

    found is False when the path does not apply to this node (for example
    `func.name` when func is a Call). The predicate is then simply false.
    """
    cur = node
    for seg in path:
        if not isinstance(cur, ASTNode):
            return False, None
        if attribute_kind(cur.node_type, seg) is None:
            return False, None
        cur = getattr(cur, seg)
    return True, cur


def _equal(a, b):
    if isinstance(a, ASTNode) or isinstance(b, ASTNode):
        return a is b
    if isinstance(a, bool) != isinstance(b, bool):   # keep True != 1
        return False
    return a == b


def compare(op, left, right):
    if op == "==":
        return _equal(left, right)
    if op == "!=":
        return not _equal(left, right)
    both_num = all(isinstance(v, (int, float)) and not isinstance(v, bool)
                   for v in (left, right))
    both_str = isinstance(left, str) and isinstance(right, str)
    if not (both_num or both_str):
        return False
    return {"<": left < right, ">": left > right,
            "<=": left <= right, ">=": left >= right}[op]


def extract_snippet(source, node):
    """Source text covered by `node`, using its recorded positions."""
    lines = source.split("\n")
    sl, sc = node.lineno - 1, node.col_offset
    el, ec = node.end_lineno - 1, node.end_col_offset
    if sl == el:
        return lines[sl][sc:ec]
    parts = [lines[sl][sc:]] + lines[sl + 1:el] + [lines[el][:ec]]
    return "\n".join(parts)


@dataclass
class Match:
    node: ASTNode = field(repr=False)
    node_type: str
    line: int
    column: int              # 1-based, as editors show it
    end_line: int
    end_column: int
    snippet: str
    bindings: dict

    def to_dict(self):
        return {"node_type": self.node_type, "line": self.line,
                "column": self.column, "end_line": self.end_line,
                "end_column": self.end_column, "snippet": self.snippet,
                "bindings": self.bindings}
