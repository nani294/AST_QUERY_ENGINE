"""Token class and small helpers that do not depend on SLY."""
from bisect import bisect_right
from dataclasses import dataclass


@dataclass
class Token:
    """One token of the source language, after the layout stage.

    col / end_col are 0-based. (end_lineno, end_col) is the position just
    AFTER the last character. Synthetic tokens (INDENT, DEDENT, and the
    NEWLINE added at end of file) are zero-width: raw == ''.
    """
    type: str
    value: object
    lineno: int
    col: int
    end_lineno: int
    end_col: int
    index: int          # absolute character offset in the source
    raw: str = ""       # the exact text matched

    # Same names the AST nodes use, so tokens and nodes can be treated alike.
    @property
    def col_offset(self):
        return self.col

    @property
    def end_col_offset(self):
        return self.end_col

    @property
    def end(self):
        return self.index + len(self.raw)


class LineIndex:
    """Converts an absolute character offset into (line, column)."""

    def __init__(self, source):
        self.starts = [0]
        for i, ch in enumerate(source):
            if ch == "\n":
                self.starts.append(i + 1)

    def locate(self, index):
        line = bisect_right(self.starts, index)      # 1-based line number
        return line, index - self.starts[line - 1]


_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "\\": "\\",
            "'": "'", '"': '"', "0": "\0"}


def decode_string(raw):
    """Turn the text of a string literal (with quotes) into its value."""
    body = raw[3:-3] if raw[:3] in ('"""', "'''") and len(raw) >= 6 else raw[1:-1]
    out = []
    i = 0
    while i < len(body):
        ch = body[i]
        if ch == "\\" and i + 1 < len(body):
            nxt = body[i + 1]
            if nxt == "\n":                 # backslash-newline inside a string
                i += 2
                continue
            out.append(_ESCAPES.get(nxt, "\\" + nxt))
            i += 2
        else:
            out.append(ch)
            i += 1
    return "".join(out)
