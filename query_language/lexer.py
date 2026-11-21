"""Lexical analysis for the query language, written with SLY.

    Call(func.name == "open") AND NOT ancestor(With)
    -> IDENTIFIER LPAREN IDENTIFIER DOT IDENTIFIER EQ STRING RPAREN AND NOT
       ANCESTOR LPAREN IDENTIFIER RPAREN

Whitespace, newlines and #-comments are ignored (queries may span lines).
"""
from dataclasses import dataclass

from sly import Lexer

from source_parser.tokens import decode_string
from .errors import QueryLexicalError


class QueryLexer(Lexer):
    tokens = {
        IDENTIFIER, STRING, NUMBER, METAVARIABLE,
        AND, OR, NOT, TRUE, FALSE, NONE,
        PARENT, ANCESTOR, DESCENDANT,
        EQ, NE, LE, GE, LT, GT,
        LPAREN, RPAREN, DOT, COMMA,
    }

    ignore = ' \t\r'
    ignore_comment = r'\#.*'

    @_(r'\n+')
    def ignore_newline(self, t):
        self.lineno += t.value.count('\n')

    STRING = r'"(?:[^"\\\n]|\\.)*"|\'(?:[^\'\\\n]|\\.)*\''
    METAVARIABLE = r'\$[A-Za-z_][A-Za-z0-9_]*'
    NUMBER = r'-?\d+(?:\.\d+)?'

    IDENTIFIER = r'[A-Za-z_][A-Za-z0-9_]*'
    IDENTIFIER['AND'] = AND
    IDENTIFIER['and'] = AND
    IDENTIFIER['OR'] = OR
    IDENTIFIER['or'] = OR
    IDENTIFIER['NOT'] = NOT
    IDENTIFIER['not'] = NOT
    IDENTIFIER['True'] = TRUE
    IDENTIFIER['False'] = FALSE
    IDENTIFIER['None'] = NONE
    IDENTIFIER['parent'] = PARENT
    IDENTIFIER['ancestor'] = ANCESTOR
    IDENTIFIER['descendant'] = DESCENDANT

    # two-character operators before their one-character prefixes
    EQ = r'=='
    NE = r'!='
    LE = r'<='
    GE = r'>='
    LT = r'<'
    GT = r'>'
    LPAREN = r'\('
    RPAREN = r'\)'
    DOT = r'\.'
    COMMA = r','

    def error(self, t):
        text = getattr(self, 'query_text', '')
        lineno, col = locate(text, t.index)
        ch = t.value[0]
        if ch in '"\'':
            raise QueryLexicalError("Unterminated string literal", lineno, col)
        raise QueryLexicalError(f"Illegal character {ch!r}", lineno, col)


# Lowercase on purpose: inside a SLY Parser class body, SLY replaces any unknown
# ALL-CAPS name with a plain string, so `tokens = QUERY_TOKEN_NAMES` would break.
query_token_names = set(QueryLexer.tokens)


@dataclass
class QToken:
    type: str
    value: object
    lineno: int
    col: int
    index: int
    raw: str

    @property
    def end(self):
        return self.index + len(self.raw)


def locate(text, index):
    """(line, 0-based column) of a character offset."""
    line = text.count('\n', 0, index) + 1
    col = index - (text.rfind('\n', 0, index) + 1)
    return line, col


def tokenize_query(text):
    """Query text -> list of QToken (values decoded)."""
    text = text.replace('\r\n', '\n')
    lexer = QueryLexer()
    lexer.query_text = text
    out = []
    for t in lexer.tokenize(text):
        raw = t.value
        if t.type == 'NUMBER':
            value = float(raw) if '.' in raw else int(raw)
        elif t.type == 'STRING':
            value = decode_string(raw)
        else:
            value = raw
        line, col = locate(text, t.index)
        out.append(QToken(t.type, value, line, col, t.index, raw))
    return out


def dump_query_tokens(tokens):
    rows = []
    for t in tokens:
        shown = repr(t.value) if t.type in ('IDENTIFIER', 'STRING', 'NUMBER', 'METAVARIABLE') else ''
        rows.append(f"{t.lineno:>3}:{t.col:<3} {t.type:<12} {shown}".rstrip())
    return "\n".join(rows)
