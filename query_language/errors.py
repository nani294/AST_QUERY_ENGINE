"""Error types for the query language (lexing, parsing, semantic analysis)."""

PRETTY = {
    "IDENTIFIER": "identifier", "STRING": "string", "NUMBER": "number",
    "METAVARIABLE": "metavariable", "LPAREN": "'('", "RPAREN": "')'",
    "DOT": "'.'", "COMMA": "','", "EQ": "'=='", "NE": "'!='", "LT": "'<'",
    "GT": "'>'", "LE": "'<='", "GE": "'>='", "$end": "end of query",
}
COMPARISONS = {"EQ", "NE", "LT", "GT", "LE", "GE"}
VALUES = {"STRING", "NUMBER", "METAVARIABLE", "TRUE", "FALSE", "NONE"}
RELATIONS = {"PARENT", "ANCESTOR", "DESCENDANT"}


def describe_expected(names):
    names = set(names)
    if len(names) > 1:
        names.discard("$end")
    parts = []
    if VALUES <= names:
        parts.append("value")
        names -= VALUES
    if COMPARISONS <= names:
        parts.append("comparison operator")
        names -= COMPARISONS
    if RELATIONS <= names and "IDENTIFIER" in names:
        parts.append("node type or relationship")
        names -= RELATIONS | {"IDENTIFIER"}
    for n in sorted(names):
        parts.append(PRETTY.get(n, n))
    if len(parts) > 6:
        parts = parts[:6] + ["..."]
    return " or ".join(parts) if len(parts) <= 2 else ", ".join(parts)


class QueryError(Exception):
    """Lexical or syntax error in a query."""

    def __init__(self, message, lineno=None, column=None,
                 unexpected=None, expected=None):
        super().__init__(message)
        self.message = message
        self.lineno = lineno
        self.column = column            # 0-based; printed 1-based
        self.unexpected = unexpected
        self.expected = expected

    def format(self):
        lines = ["Query Error", "-----------"]
        if self.lineno is not None:
            lines.append(f"Line: {self.lineno}")
            lines.append(f"Column: {self.column + 1}")
        lines.append("")
        if self.unexpected is not None:
            lines.append(f"Unexpected token: {self.unexpected}")
            if self.expected:
                lines.append(f"Expected: {self.expected}")
        else:
            lines.append(self.message)
        return "\n".join(lines)


class QueryLexicalError(QueryError):
    """Illegal character or unterminated string in a query."""


class SemanticIssue:
    def __init__(self, message, lineno=None, column=None, hint=None):
        self.message = message
        self.lineno = lineno
        self.column = column
        self.hint = hint


class QuerySemanticError(Exception):
    """The query parsed, but it does not make sense. Holds every problem found."""

    def __init__(self, issues):
        self.issues = list(issues)
        super().__init__("; ".join(i.message for i in self.issues))

    @property
    def message(self):
        return "; ".join(i.message for i in self.issues)

    def format(self):
        blocks = []
        for i in self.issues:
            lines = ["Semantic Error:", i.message]
            if i.hint:
                lines.append(i.hint)
            if i.lineno is not None:
                lines.append(f"(at line {i.lineno}, column {i.column + 1})")
            blocks.append("\n".join(lines))
        return "\n\n".join(blocks)
