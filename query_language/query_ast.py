"""Query AST: the tree a parsed query becomes (separate from the source AST)."""
import json


class QueryNode:
    _fields = ()

    def __init__(self, *args, lineno=None, col=None):
        if len(args) != len(self._fields):
            raise TypeError(f"{type(self).__name__} needs {len(self._fields)} "
                            f"fields, got {len(args)}")
        for name, value in zip(self._fields, args):
            setattr(self, name, value)
        self.lineno = lineno
        self.col = col                  # 0-based

    def __eq__(self, other):            # structural; positions are ignored
        return type(self) is type(other) and all(
            getattr(self, f) == getattr(other, f) for f in self._fields)

    __hash__ = None

    def __repr__(self):
        inner = ", ".join(repr(getattr(self, f)) for f in self._fields)
        return f"{type(self).__name__}({inner})"

    def __str__(self):
        return format_query(self)

    def children(self):
        return [getattr(self, f) for f in self._fields
                if isinstance(getattr(self, f), QueryNode)]


class NodeMatch(QueryNode):
    """`Call` or `Call(<predicate>)`: match nodes of one source-AST type."""
    _fields = ("node_type", "predicate")


class Predicate(QueryNode):
    """`func.name == "open"`: compare an attribute path with a value."""
    _fields = ("path", "op", "value")


class Literal(QueryNode):
    _fields = ("value",)


class MetaVariable(QueryNode):
    """`$X`: binds to whatever value it first meets, then must match again."""
    _fields = ("name",)


class And(QueryNode):
    _fields = ("left", "right")


class Or(QueryNode):
    _fields = ("left", "right")


class Not(QueryNode):
    _fields = ("operand",)


class Parent(QueryNode):
    _fields = ("operand",)


class Ancestor(QueryNode):
    _fields = ("operand",)


class Descendant(QueryNode):
    _fields = ("operand",)


RELATIONS = {"parent": Parent, "ancestor": Ancestor, "descendant": Descendant}


def _literal(value):
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if value is None or isinstance(value, bool):
        return str(value)
    return repr(value)


def format_query(q, outer=0):
    """Canonical text of a query (precedence: OR < AND < NOT)."""
    if isinstance(q, NodeMatch):
        if q.predicate is None:
            return q.node_type
        return f"{q.node_type}({format_query(q.predicate)})"
    if isinstance(q, Predicate):
        return f"{'.'.join(q.path)} {q.op} {format_query(q.value)}"
    if isinstance(q, Literal):
        return _literal(q.value)
    if isinstance(q, MetaVariable):
        return q.name
    if isinstance(q, Or):
        s, prec = f"{format_query(q.left, 1)} OR {format_query(q.right, 2)}", 1
    elif isinstance(q, And):
        s, prec = f"{format_query(q.left, 2)} AND {format_query(q.right, 3)}", 2
    elif isinstance(q, Not):
        s, prec = f"NOT {format_query(q.operand, 3)}", 3
    else:                                # Parent / Ancestor / Descendant
        return f"{type(q).__name__.lower()}({format_query(q.operand)})"
    return f"({s})" if prec < outer else s


def dump_query(q, prefix="", is_last=True, is_root=True):
    """ASCII tree, e.g.

        AND
        +-- NodeMatch(Call)
        |   +-- Predicate: func.name == "open"
        +-- NOT
            +-- Ancestor
                +-- NodeMatch(With)
    """
    if isinstance(q, NodeMatch):
        label = f"NodeMatch({q.node_type})"
    elif isinstance(q, Predicate):
        label = f"Predicate: {format_query(q)}"
    elif isinstance(q, (And, Or, Not)):
        label = type(q).__name__.upper()
    else:
        label = type(q).__name__
    kids = [] if isinstance(q, Predicate) else q.children()
    if isinstance(q, NodeMatch) and q.predicate is not None:
        kids = [q.predicate]
    if is_root:
        lines, child_prefix = [label], ""
    else:
        lines = [prefix + ("+-- ") + label]
        child_prefix = prefix + ("    " if is_last else "|   ")
    for i, kid in enumerate(kids):
        lines.append(dump_query(kid, child_prefix, i == len(kids) - 1, False))
    return "\n".join(lines)
