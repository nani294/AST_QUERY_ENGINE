"""Layout stage: raw lexer tokens -> final tokens with INDENT / DEDENT.

SLY's lexer is regex-based and stateless between tokens, so it cannot know
about indentation levels. This stage adds that memory (a stack of levels),
exactly as CPython's own tokenizer does. It does not import SLY.
"""
from .errors import SourceIndentationError
from .tokens import LineIndex, Token, decode_string

TAB_SIZE = 8
OPENERS = {"LPAREN", "LBRACKET"}
CLOSERS = {"RPAREN", "RBRACKET"}


def indent_width(prefix):
    """Width of leading whitespace; a tab advances to the next multiple of 8."""
    width = 0
    for ch in prefix:
        width = (width // TAB_SIZE + 1) * TAB_SIZE if ch == "\t" else width + 1
    return width


def to_token(raw_tok, lines):
    """Convert a raw lexer token (needs .type .value .index) into a Token."""
    raw = raw_tok.value
    lineno, col = lines.locate(raw_tok.index)
    end_lineno, end_col = lines.locate(raw_tok.index + len(raw))
    if raw_tok.type == "NUMBER":
        value = float(raw) if "." in raw else int(raw)
    elif raw_tok.type == "STRING":
        value = decode_string(raw)
    else:
        value = raw
    return Token(raw_tok.type, value, lineno, col, end_lineno, end_col,
                 raw_tok.index, raw)


def _synthetic(type_, index, lines):
    lineno, col = lines.locate(index)
    return Token(type_, "", lineno, col, lineno, col, index, "")


def apply_layout(raw_tokens, source):
    """Insert INDENT/DEDENT, drop blank-line and in-bracket NEWLINEs."""
    lines = LineIndex(source)
    out = []
    indents = [0]            # stack of active indentation widths
    depth = 0                # how many ( or [ are currently open
    at_line_start = True

    for rt in raw_tokens:
        if rt.type == "NEWLINE":
            # blank line, or a newline inside brackets: no logical newline
            if at_line_start or depth > 0:
                continue
            out.append(to_token(rt, lines))
            at_line_start = True
            continue

        if at_line_start:
            lineno, col = lines.locate(rt.index)
            width = indent_width(source[rt.index - col:rt.index])
            if width > indents[-1]:
                indents.append(width)
                out.append(_synthetic("INDENT", rt.index, lines))
            else:
                while width < indents[-1]:
                    indents.pop()
                    out.append(_synthetic("DEDENT", rt.index, lines))
                if width != indents[-1]:
                    raise SourceIndentationError(
                        "Unindent does not match any outer indentation level",
                        lineno, col)
            at_line_start = False

        if rt.type in OPENERS:
            depth += 1
        elif rt.type in CLOSERS:
            depth = max(0, depth - 1)
        out.append(to_token(rt, lines))

    # end of file: close the last line, then close every open block
    if not at_line_start and out:
        last = out[-1]
        out.append(_synthetic("NEWLINE", last.index + len(last.raw), lines))
    while len(indents) > 1:
        indents.pop()
        out.append(_synthetic("DEDENT", len(source), lines))
    return out
