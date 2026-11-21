"""Custom AST for the Python subset (built by the parser, no `ast` module).

Every node stores its source location:
    lineno, col_offset          where it starts (line 1-based, column 0-based)
    end_lineno, end_col_offset  just after where it ends

ATTRIBUTE_SCHEMA at the bottom lists the attributes a query may read on each
node type. The semantic analyzer validates queries against it and the
evaluator uses it to resolve paths like `func.name`.
"""


class ASTNode:
    _fields = ()          # field names, in source order (drives children())
    _list_fields = ()     # fields that default to an empty list

    def __init__(self, *args, lineno=None, col_offset=None,
                 end_lineno=None, end_col_offset=None, **kwargs):
        if len(args) > len(self._fields):
            raise TypeError(f"{type(self).__name__} takes at most "
                            f"{len(self._fields)} fields, got {len(args)}")
        values = dict(zip(self._fields, args))
        for key in kwargs:
            if key not in self._fields:
                raise TypeError(f"{type(self).__name__} has no field '{key}'")
        values.update(kwargs)
        for name in self._fields:
            default = [] if name in self._list_fields else None
            setattr(self, name, values.get(name, default))
        self.lineno = lineno
        self.col_offset = col_offset
        self.end_lineno = end_lineno
        self.end_col_offset = end_col_offset

    @property
    def node_type(self):
        return type(self).__name__

    @property
    def line_count(self):
        if self.lineno is None or self.end_lineno is None:
            return None
        return self.end_lineno - self.lineno + 1

    def children(self):
        """Child nodes in source order (used by the traversal engine)."""
        out = []
        for name in self._fields:
            value = getattr(self, name)
            if isinstance(value, ASTNode):
                out.append(value)
            elif isinstance(value, list):
                out.extend(v for v in value if isinstance(v, ASTNode))
        return out

    def __repr__(self):
        return f"<{self.node_type} {self.lineno}:{self.col_offset}>"


# ---------------------------------------------------------------- helpers
_BLOCK_FIELDS = ("body", "orelse", "finalbody")
_COMPOUND = ("If", "For", "While", "With", "Try")


def _count_statements(node):
    total = 0
    for field in _BLOCK_FIELDS:
        for stmt in getattr(node, field, None) or []:
            total += 1 + _count_statements(stmt)
    for handler in getattr(node, "handlers", None) or []:
        total += _count_statements(handler)
    return total


def _nesting(node):
    inner = 0
    for field in _BLOCK_FIELDS:
        for stmt in getattr(node, field, None) or []:
            inner = max(inner, _nesting(stmt))
    for handler in getattr(node, "handlers", None) or []:
        inner = max(inner, _nesting(handler))
    if node.node_type in _COMPOUND:
        is_elif = node.node_type == "If" and node.is_elif
        return (0 if is_elif else 1) + inner
    return inner


def _count_returns(node):
    total = 0
    for child in node.children():
        if child.node_type == "FunctionDef":
            continue                      # returns of nested functions are not ours
        total += (1 if child.node_type == "Return" else 0) + _count_returns(child)
    return total


# ------------------------------------------------------------ module level
class Program(ASTNode):
    _fields = ("body",)
    _list_fields = ("body",)

    @property
    def num_statements(self):
        return _count_statements(self)


class FunctionDef(ASTNode):
    _fields = ("name", "params", "body")
    _list_fields = ("params", "body")

    @property
    def num_params(self):
        return len(self.params)

    @property
    def num_returns(self):
        return _count_returns(self)

    @property
    def num_statements(self):
        return _count_statements(self)

    @property
    def max_nesting(self):
        return _nesting(self)


class Parameter(ASTNode):
    _fields = ("name", "default")


# -------------------------------------------------------------- statements
class Assign(ASTNode):
    _fields = ("target", "value")


class If(ASTNode):
    """`elif` is stored as an If inside orelse, with is_elif=True."""
    _fields = ("test", "body", "orelse", "is_elif")
    _list_fields = ("body", "orelse")

    @property
    def has_else(self):
        """True if the whole if/elif chain ends with an `else:` block."""
        node = self
        while (len(node.orelse) == 1 and node.orelse[0].node_type == "If"
               and node.orelse[0].is_elif):
            node = node.orelse[0]
        return bool(node.orelse)


class For(ASTNode):
    _fields = ("target", "iter", "body")
    _list_fields = ("body",)


class While(ASTNode):
    _fields = ("test", "body")
    _list_fields = ("body",)


class With(ASTNode):
    _fields = ("items", "body")
    _list_fields = ("items", "body")

    @property
    def num_items(self):
        return len(self.items)


class WithItem(ASTNode):
    _fields = ("context_expr", "optional_vars")


class Return(ASTNode):
    _fields = ("value",)

    @property
    def has_value(self):
        return self.value is not None


class Try(ASTNode):
    _fields = ("body", "handlers", "finalbody")
    _list_fields = ("body", "handlers", "finalbody")

    @property
    def has_finally(self):
        return bool(self.finalbody)

    @property
    def num_handlers(self):
        return len(self.handlers)


class ExceptHandler(ASTNode):
    _fields = ("type", "name", "body")
    _list_fields = ("body",)

    @property
    def is_bare(self):
        return self.type is None


class Import(ASTNode):
    """`import a, b` -> module=None; `from m import x` -> module='m', is_from."""
    _fields = ("module", "names", "is_from")
    _list_fields = ("names",)

    @property
    def num_names(self):
        return len(self.names)


class Alias(ASTNode):
    _fields = ("name", "asname")


class Pass(ASTNode):
    pass


class Break(ASTNode):
    pass


class Continue(ASTNode):
    pass


# ------------------------------------------------------------- expressions
class Name(ASTNode):
    _fields = ("id",)

    @property
    def name(self):
        return self.id

    @property
    def qualname(self):
        return self.id


class Constant(ASTNode):
    _fields = ("value",)

    @property
    def kind(self):
        v = self.value
        if v is None:
            return "None"
        if isinstance(v, bool):
            return "bool"
        if isinstance(v, int):
            return "int"
        if isinstance(v, float):
            return "float"
        return "str"


class Call(ASTNode):
    _fields = ("func", "args", "keywords")
    _list_fields = ("args", "keywords")

    @property
    def num_args(self):
        return len(self.args)

    @property
    def num_keywords(self):
        return len(self.keywords)


class Keyword(ASTNode):
    _fields = ("arg", "value")


class Attribute(ASTNode):
    _fields = ("value", "attr")

    @property
    def name(self):
        return self.attr

    @property
    def qualname(self):
        base = getattr(self.value, "qualname", None) \
            if self.value.node_type in ("Name", "Attribute") else None
        return f"{base}.{self.attr}" if base else None


class Subscript(ASTNode):
    _fields = ("value", "index")


class BinaryOp(ASTNode):
    _fields = ("op", "left", "right")


class UnaryOp(ASTNode):
    _fields = ("op", "operand")


class Compare(ASTNode):
    _fields = ("left", "ops", "comparators")
    _list_fields = ("ops", "comparators")

    @property
    def op(self):
        return self.ops[0]

    @property
    def num_comparators(self):
        return len(self.comparators)


class BoolOp(ASTNode):
    _fields = ("op", "values")
    _list_fields = ("values",)


class Tuple(ASTNode):
    _fields = ("elts",)
    _list_fields = ("elts",)

    @property
    def num_elements(self):
        return len(self.elts)


class List(ASTNode):
    _fields = ("elts",)
    _list_fields = ("elts",)

    @property
    def num_elements(self):
        return len(self.elts)


NODE_CLASSES = {cls.__name__: cls for cls in ASTNode.__subclasses__()}
LEAF_TYPES = {"Name", "Constant", "Pass", "Break", "Continue", "Alias"}

# ------------------------------------------------------------------ schema
# Kinds: 'str' 'int' 'bool' 'any'  or  ('node', (possible node types...))
EXPR = ("Name", "Constant", "Call", "Attribute", "Subscript", "BinaryOp",
        "UnaryOp", "Compare", "BoolOp", "Tuple", "List")
TARGET = ("Name", "Attribute", "Subscript", "Tuple", "List")


def _node(types):
    return ("node", tuple(types))


UNIVERSAL_ATTRIBUTES = {
    "lineno": "int", "col_offset": "int",
    "end_lineno": "int", "end_col_offset": "int", "line_count": "int",
}

ATTRIBUTE_SCHEMA = {
    "Program": {"num_statements": "int"},
    "FunctionDef": {"name": "str", "num_params": "int", "num_returns": "int",
                    "num_statements": "int", "max_nesting": "int"},
    "Parameter": {"name": "str", "default": _node(EXPR)},
    "Assign": {"target": _node(TARGET), "value": _node(EXPR)},
    "If": {"test": _node(EXPR), "is_elif": "bool", "has_else": "bool"},
    "For": {"target": _node(("Name", "Tuple")), "iter": _node(EXPR)},
    "While": {"test": _node(EXPR)},
    "With": {"num_items": "int"},
    "WithItem": {"context_expr": _node(EXPR), "optional_vars": _node(("Name",))},
    "Return": {"value": _node(EXPR), "has_value": "bool"},
    "Try": {"has_finally": "bool", "num_handlers": "int"},
    "ExceptHandler": {"type": _node(EXPR), "name": "str", "is_bare": "bool"},
    "Import": {"module": "str", "is_from": "bool", "num_names": "int"},
    "Alias": {"name": "str", "asname": "str"},
    "Pass": {}, "Break": {}, "Continue": {},
    "Name": {"id": "str", "name": "str", "qualname": "str"},
    "Constant": {"value": "any", "kind": "str"},
    "Call": {"func": _node(EXPR), "num_args": "int", "num_keywords": "int"},
    "Keyword": {"arg": "str", "value": _node(EXPR)},
    "Attribute": {"value": _node(EXPR), "attr": "str", "name": "str",
                  "qualname": "str"},
    "Subscript": {"value": _node(EXPR), "index": _node(EXPR)},
    "BinaryOp": {"op": "str", "left": _node(EXPR), "right": _node(EXPR)},
    "UnaryOp": {"op": "str", "operand": _node(EXPR)},
    "Compare": {"left": _node(EXPR), "op": "str", "num_comparators": "int"},
    "BoolOp": {"op": "str"},
    "Tuple": {"num_elements": "int"},
    "List": {"num_elements": "int"},
}


def attributes_of(type_name):
    """All queryable attributes of a node type (own + universal)."""
    merged = dict(UNIVERSAL_ATTRIBUTES)
    merged.update(ATTRIBUTE_SCHEMA.get(type_name, {}))
    return merged


def attribute_kind(type_name, attr):
    """Kind of `attr` on `type_name`, or None if it does not exist."""
    return attributes_of(type_name).get(attr)


# -------------------------------------------------------------------- dump
def dump(node, indent=0, label=None):
    """Readable tree for teaching/debugging (`main.py --ast FILE`)."""
    def is_child_field(v):
        return isinstance(v, ASTNode) or (
            isinstance(v, list) and all(isinstance(i, ASTNode) for i in v))

    pad = "  " * indent
    scalars = [f"{f}={getattr(node, f)!r}" for f in node._fields
               if not is_child_field(getattr(node, f))]
    head = f"{pad}{label + ': ' if label else ''}{node.node_type}"
    if scalars:
        head += " " + " ".join(scalars)
    if node.lineno is not None:
        head += (f"  [{node.lineno}:{node.col_offset}-"
                 f"{node.end_lineno}:{node.end_col_offset}]")
    lines = [head]
    for f in node._fields:
        v = getattr(node, f)
        if isinstance(v, ASTNode):
            lines.append(dump(v, indent + 1, f))
        elif isinstance(v, list) and v and is_child_field(v):
            for i, item in enumerate(v):
                lines.append(dump(item, indent + 1, f"{f}[{i}]"))
    return "\n".join(lines)
