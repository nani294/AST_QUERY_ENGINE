"""Syntax analysis for the query language, written with SLY.

Precedence (lowest to highest):  OR  <  AND  <  NOT  <  relationship / atom.
It is encoded in the layered rules or_expr -> and_expr -> not_expr -> rel_expr
-> primary, so no SLY precedence table is needed.

    primary  := Type | Type(predicates) | ( query ) | parent|ancestor|descendant ( query )
    rel_expr := primary | primary  parent|ancestor|descendant  primary      (infix form)
"""
from sly import Parser

from .errors import QueryError, describe_expected
from .lexer import query_token_names, tokenize_query
from .query_ast import (And, Ancestor, Descendant, Literal, MetaVariable,
                        NodeMatch, Not, Or, Parent, Predicate)

_REL_CLASS = {"PARENT": Parent, "ANCESTOR": Ancestor, "DESCENDANT": Descendant}


def _at(node):
    return dict(lineno=node.lineno, col=node.col)


class _ParserToken:
    __slots__ = ("type", "value", "lineno", "index", "end")

    def __init__(self, tok):
        self.type = tok.type
        self.value = tok
        self.lineno = tok.lineno
        self.index = tok.index
        self.end = tok.end


class QueryParser(Parser):
    tokens = query_token_names

    @_('or_expr')
    def query(self, p):
        return p.or_expr

    # ---- boolean structure -------------------------------------------------
    @_('or_expr OR and_expr')
    def or_expr(self, p):
        return Or(p.or_expr, p.and_expr, **_at(p.or_expr))

    @_('and_expr')
    def or_expr(self, p):
        return p.and_expr

    @_('and_expr AND not_expr')
    def and_expr(self, p):
        return And(p.and_expr, p.not_expr, **_at(p.and_expr))

    @_('not_expr')
    def and_expr(self, p):
        return p.not_expr

    @_('NOT not_expr')
    def not_expr(self, p):
        return Not(p.not_expr, lineno=p.NOT.lineno, col=p.NOT.col)

    @_('rel_expr')
    def not_expr(self, p):
        return p.rel_expr

    # ---- relationships -----------------------------------------------------
    @_('primary')
    def rel_expr(self, p):
        return p.primary

    @_('primary relop primary')
    def rel_expr(self, p):                   # FunctionDef descendant For
        cls = _REL_CLASS[p.relop.type]
        right = cls(p[2], lineno=p.relop.lineno, col=p.relop.col)
        return And(p[0], right, **_at(p[0]))

    @_('PARENT', 'ANCESTOR', 'DESCENDANT')
    def relop(self, p):
        return p[0]

    # ---- primaries ---------------------------------------------------------
    @_('IDENTIFIER')
    def primary(self, p):
        t = p.IDENTIFIER
        return NodeMatch(t.value, None, lineno=t.lineno, col=t.col)

    @_('IDENTIFIER LPAREN pred_or RPAREN')
    def primary(self, p):
        t = p.IDENTIFIER
        return NodeMatch(t.value, p.pred_or, lineno=t.lineno, col=t.col)

    @_('LPAREN or_expr RPAREN')
    def primary(self, p):
        return p.or_expr

    @_('relop LPAREN or_expr RPAREN')
    def primary(self, p):                    # ancestor(With)
        cls = _REL_CLASS[p.relop.type]
        return cls(p.or_expr, lineno=p.relop.lineno, col=p.relop.col)

    # ---- predicates (inside Type( ... )) -------------------------------------
    @_('pred_or OR pred_and')
    def pred_or(self, p):
        return Or(p.pred_or, p.pred_and, **_at(p.pred_or))

    @_('pred_and')
    def pred_or(self, p):
        return p.pred_and

    @_('pred_and AND pred_not')
    def pred_and(self, p):
        return And(p.pred_and, p.pred_not, **_at(p.pred_and))

    @_('pred_and COMMA pred_not')
    def pred_and(self, p):                   # a comma means AND
        return And(p.pred_and, p.pred_not, **_at(p.pred_and))

    @_('pred_not')
    def pred_and(self, p):
        return p.pred_not

    @_('NOT pred_not')
    def pred_not(self, p):
        return Not(p.pred_not, lineno=p.NOT.lineno, col=p.NOT.col)

    @_('pred_atom')
    def pred_not(self, p):
        return p.pred_atom

    @_('path compop value')
    def pred_atom(self, p):
        first = p.path[0]
        return Predicate([t.value for t in p.path], p.compop, p.value,
                         lineno=first.lineno, col=first.col)

    @_('LPAREN pred_or RPAREN')
    def pred_atom(self, p):
        return p.pred_or

    @_('IDENTIFIER')
    def path(self, p):
        return [p.IDENTIFIER]

    @_('path DOT IDENTIFIER')
    def path(self, p):
        return p.path + [p.IDENTIFIER]

    @_('EQ', 'NE', 'LT', 'GT', 'LE', 'GE')
    def compop(self, p):
        return p[0].raw

    @_('STRING')
    def value(self, p):
        t = p.STRING
        return Literal(t.value, lineno=t.lineno, col=t.col)

    @_('NUMBER')
    def value(self, p):
        t = p.NUMBER
        return Literal(t.value, lineno=t.lineno, col=t.col)

    @_('TRUE')
    def value(self, p):
        return Literal(True, lineno=p.TRUE.lineno, col=p.TRUE.col)

    @_('FALSE')
    def value(self, p):
        return Literal(False, lineno=p.FALSE.lineno, col=p.FALSE.col)

    @_('NONE')
    def value(self, p):
        return Literal(None, lineno=p.NONE.lineno, col=p.NONE.col)

    @_('METAVARIABLE')
    def value(self, p):
        t = p.METAVARIABLE
        return MetaVariable(t.value, lineno=t.lineno, col=t.col)

    # ---- errors ------------------------------------------------------------
    def error(self, tok):
        last = getattr(self, "last_token", None)
        if tok is None or getattr(tok, "type", None) == "$end":
            shown = "end of query"
            line, col = (last.lineno, last.col + len(last.raw)) if last else (1, 0)
        else:
            t = tok.value
            shown = t.raw if t.raw.isalnum() or t.raw.startswith(('"', "'", "$")) \
                else f"'{t.raw}'"
            line, col = t.lineno, t.col
        try:
            state = self.statestack[-1]
            expected = describe_expected(self._lrtable.lr_action[state].keys())
        except Exception:
            expected = None
        raise QueryError("Syntax error", line, col, unexpected=shown,
                         expected=expected)


def parse_query(text):
    """Query text -> Query AST (raises QueryError on bad input)."""
    tokens = tokenize_query(text)
    if not tokens:
        raise QueryError("The query is empty", 1, 0)
    parser = QueryParser()
    parser.last_token = tokens[-1]
    return parser.parse(iter([_ParserToken(t) for t in tokens]))
