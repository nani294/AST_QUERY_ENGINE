"""Error types for the source-language front end.

Every error carries a line and a 0-based column. format() prints the
column 1-based, which is what editors show.
"""

# Token groups used to turn a raw "expected" set into a readable sentence.
EXPR_START = {"IDENTIFIER", "NUMBER", "STRING", "TRUE", "FALSE", "NONE",
              "LPAREN", "LBRACKET", "MINUS", "PLUS"}
OPERATORS = {"PLUS", "MINUS", "MULTIPLY", "DIVIDE", "MODULO", "EQ", "NE", "LT",
             "GT", "LE", "GE", "AND", "OR", "NOT", "IN", "IS", "DOT",
             "LPAREN", "LBRACKET"}
PRETTY = {
    "IDENTIFIER": "identifier", "NUMBER": "number", "STRING": "string",
    "LPAREN": "'('", "RPAREN": "')'", "LBRACKET": "'['", "RBRACKET": "']'",
    "COLON": "':'", "COMMA": "','", "DOT": "'.'", "ASSIGN": "'='",
    "NEWLINE": "end of line", "INDENT": "an indented block",
    "DEDENT": "end of block", "$end": "end of file",
}


def describe_unexpected(token):
    """Human-readable description of the token the parser could not accept."""
    if token is None or getattr(token, "type", None) == "$end":
        return "end of file"
    if token.type == "NEWLINE":
        return "end of line"
    if token.type == "INDENT":
        return "indent (unexpected indentation)"
    if token.type == "DEDENT":
        return "dedent"
    raw = token.raw
    return raw if raw.isalnum() or raw.startswith(('"', "'")) else f"'{raw}'"


def describe_expected(names):
    """Compress a set of acceptable token names into a short phrase."""
    names = set(names) - {"$end"} if len(names) > 1 else set(names)
    if not names:
        return None
    parts = []
    if EXPR_START <= names:
        parts.append("expression")
        names -= EXPR_START
        names.discard("NOT")             # 'not x' is part of "expression" too
    structural = [n for n in names if n not in OPERATORS]
    operators_present = any(n in OPERATORS for n in names)
    for n in sorted(structural):
        parts.append(PRETTY.get(n, n.lower()))
    if operators_present:
        parts.append("an operator")
    if len(parts) > 6:
        parts = parts[:6] + ["..."]
    return " or ".join(parts) if len(parts) <= 2 else ", ".join(parts)


class SourceError(Exception):
    kind = "Source Error"

    def __init__(self, message, lineno=None, column=None):
        super().__init__(message)
        self.message = message
        self.lineno = lineno
        self.column = column

    def format(self):
        lines = [f"{self.kind}:"]
        if self.lineno is not None:
            col = "?" if self.column is None else self.column + 1
            lines.append(f"Line {self.lineno}, Column {col}")
        lines.append("")
        lines.append(self.message)
        return "\n".join(lines)


class LexicalError(SourceError):
    """An illegal character or unterminated string."""
    kind = "Lexical Error"


class SourceIndentationError(SourceError):
    """Inconsistent indentation (a dedent that matches no outer level)."""
    kind = "Indentation Error"


class SourceSyntaxError(SourceError):
    """The tokens do not form a valid program."""
    kind = "Syntax Error"

    def __init__(self, message, lineno=None, column=None,
                 unexpected=None, expected=None):
        super().__init__(message, lineno, column)
        self.unexpected = unexpected
        self.expected = expected

    def format(self):
        if self.unexpected is None:
            return super().format()
        lines = [f"{self.kind}:",
                 f"Line {self.lineno}, Column {self.column + 1}", "",
                 f"Unexpected token: {self.unexpected}"]
        if self.expected:
            lines.append(f"Expected: {self.expected}")
        return "\n".join(lines)
