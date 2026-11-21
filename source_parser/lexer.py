"""Lexical analysis for the Python subset, written with SLY.

Stage 2a: PythonLexer (SLY) cuts the text into raw tokens.
Stage 2b: apply_layout (indentation.py) adds INDENT / DEDENT.
tokenize() runs both.
"""
from sly import Lexer

from .errors import LexicalError
from .indentation import apply_layout, to_token
from .tokens import LineIndex


class PythonLexer(Lexer):
    tokens = {
        IDENTIFIER, NUMBER, STRING,
        # keywords
        DEF, IF, ELIF, ELSE, FOR, WHILE, IN, RETURN, WITH, AS, TRY, EXCEPT,
        FINALLY, IMPORT, FROM, PASS, BREAK, CONTINUE, AND, OR, NOT, IS,
        TRUE, FALSE, NONE,
        # operators
        EQ, NE, LE, GE, LT, GT, ASSIGN,
        PLUS, MINUS, MULTIPLY, DIVIDE, MODULO,
        # punctuation
        LPAREN, RPAREN, LBRACKET, RBRACKET, COLON, COMMA, DOT,
        NEWLINE,
    }

    ignore = ' \t'                       # spaces between tokens
    ignore_comment = r'\#.*'             # comments produce no token

    @_(r'\\\n')
    def ignore_continuation(self, t):    # backslash at end of line
        self.lineno += 1

    @_(r'"""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\'|"(?:[^"\\\n]|\\.)*"|\'(?:[^\'\\\n]|\\.)*\'')
    def STRING(self, t):
        self.lineno += t.value.count('\n')
        return t

    IDENTIFIER = r'[A-Za-z_][A-Za-z0-9_]*'
    IDENTIFIER['def'] = DEF
    IDENTIFIER['if'] = IF
    IDENTIFIER['elif'] = ELIF
    IDENTIFIER['else'] = ELSE
    IDENTIFIER['for'] = FOR
    IDENTIFIER['while'] = WHILE
    IDENTIFIER['in'] = IN
    IDENTIFIER['return'] = RETURN
    IDENTIFIER['with'] = WITH
    IDENTIFIER['as'] = AS
    IDENTIFIER['try'] = TRY
    IDENTIFIER['except'] = EXCEPT
    IDENTIFIER['finally'] = FINALLY
    IDENTIFIER['import'] = IMPORT
    IDENTIFIER['from'] = FROM
    IDENTIFIER['pass'] = PASS
    IDENTIFIER['break'] = BREAK
    IDENTIFIER['continue'] = CONTINUE
    IDENTIFIER['and'] = AND
    IDENTIFIER['or'] = OR
    IDENTIFIER['not'] = NOT
    IDENTIFIER['is'] = IS
    IDENTIFIER['True'] = TRUE
    IDENTIFIER['False'] = FALSE
    IDENTIFIER['None'] = NONE

    NUMBER = r'\d+(?:\.\d+)?'

    # two-character operators MUST come before their one-character prefixes
    EQ = r'=='
    NE = r'!='
    LE = r'<='
    GE = r'>='
    LT = r'<'
    GT = r'>'
    ASSIGN = r'='
    PLUS = r'\+'
    MINUS = r'-'
    MULTIPLY = r'\*'
    DIVIDE = r'/'
    MODULO = r'%'
    LPAREN = r'\('
    RPAREN = r'\)'
    LBRACKET = r'\['
    RBRACKET = r'\]'
    COLON = r':'
    COMMA = r','
    DOT = r'\.'

    @_(r'\n')
    def NEWLINE(self, t):
        self.lineno += 1
        return t

    def error(self, t):
        source = getattr(self, 'source_text', '')
        lineno, col = LineIndex(source).locate(t.index)
        ch = t.value[0]
        if ch in '"\'':
            raise LexicalError("Unterminated string literal", lineno, col)
        raise LexicalError(f"Illegal character {ch!r}", lineno, col)


# The parser also needs the two tokens the layout stage invents.
# Lowercase on purpose: inside a SLY Parser class body, SLY replaces any unknown
# ALL-CAPS name with a plain string, so `tokens = TOKEN_NAMES` would break.
token_names = set(PythonLexer.tokens) | {'INDENT', 'DEDENT'}


def normalize_source(source):
    """Use '\\n' line endings everywhere (Windows files have '\\r\\n')."""
    return source.replace('\r\n', '\n').replace('\r', '\n')


def _raw(source):
    lexer = PythonLexer()
    lexer.source_text = source
    return lexer.tokenize(source)


def raw_tokens(source):
    """Stage 2a only: SLY tokens, no INDENT/DEDENT (for teaching/debugging)."""
    source = normalize_source(source)
    lines = LineIndex(source)
    return [to_token(t, lines) for t in _raw(source)]


def tokenize(source):
    """Stage 2a + 2b: the full token list the parser will consume."""
    source = normalize_source(source)
    return apply_layout(_raw(source), source)


def dump_tokens(tokens):
    rows = []
    for t in tokens:
        shown = repr(t.value) if t.type in ('IDENTIFIER', 'NUMBER', 'STRING') else ''
        rows.append(f"{t.lineno:>3}:{t.col:<3} {t.type:<11} {shown}".rstrip())
    return "\n".join(rows)
