"""Syntax analysis for the Python subset, written with SLY.

The parser consumes the token list from lexer.tokenize() and builds our
custom AST. The grammar is layered by operator precedence, so it needs no
SLY `precedence` table:

    expr (or)  <  and_test  <  not_test  <  comparison  <  arith (+ -)
               <  term (* / %)  <  factor (unary + -)  <  postfix  <  atom

Each terminal handed to a rule is our own Token object (see _ParserToken), so
rules can read positions and build accurate source spans for every node.
"""
from sly import Parser

from .ast_nodes import (
    Alias, Assign, Attribute, BinaryOp, BoolOp, Break, Call, Compare,
    Constant, Continue, ExceptHandler, For, FunctionDef, If, Import, Keyword,
    List, Name, Parameter, Pass, Program, Return, Subscript, Try, Tuple,
    UnaryOp, While, With, WithItem,
)
from .errors import SourceSyntaxError, describe_expected, describe_unexpected
from .lexer import token_names, normalize_source, tokenize
from .tokens import LineIndex


# ---------------------------------------------------------- location helpers
def _start(x):
    """Where x starts, counting wrapping parentheses if it had any."""
    return getattr(x, "_ostart", None) or (x.lineno, x.col_offset)


def _end(x):
    return getattr(x, "_oend", None) or (x.end_lineno, x.end_col_offset)


def loc(first, last):
    """Source span from the start of `first` to the end of `last`."""
    if isinstance(last, list):
        last = last[-1]
    sl, sc = _start(first)
    el, ec = _end(last)
    return dict(lineno=sl, col_offset=sc, end_lineno=el, end_col_offset=ec)


def _check_target(node):
    """Only names, attributes, subscripts and tuples/lists of them can be assigned."""
    if node.node_type in ("Name", "Attribute", "Subscript"):
        return node
    if node.node_type in ("Tuple", "List"):
        for elt in node.elts:
            _check_target(elt)
        return node
    raise SourceSyntaxError(f"Cannot assign to {node.node_type}",
                            node.lineno, node.col_offset)


class _ParserToken:
    """What SLY sees: .type for the grammar, .value = our Token for the rules."""
    __slots__ = ("type", "value", "lineno", "index", "end")

    def __init__(self, tok):
        self.type = tok.type
        self.value = tok
        self.lineno = tok.lineno
        self.index = tok.index
        self.end = tok.end


class PythonParser(Parser):
    tokens = token_names

    # ------------------------------------------------------------ program
    @_('stmt_list')
    def program(self, p):
        return Program(p.stmt_list)          # span is set in parse_source()

    @_('stmt_list statement')
    def stmt_list(self, p):
        return p.stmt_list + [p.statement]

    @_('statement')
    def stmt_list(self, p):
        return [p.statement]

    @_('simple_stmt NEWLINE')
    def statement(self, p):
        return p.simple_stmt

    @_('compound_stmt')
    def statement(self, p):
        return p.compound_stmt

    @_('assignment', 'expr_stmt', 'return_stmt', 'import_stmt',
       'pass_stmt', 'break_stmt', 'continue_stmt')
    def simple_stmt(self, p):
        return p[0]

    @_('funcdef', 'if_stmt', 'for_stmt', 'while_stmt', 'with_stmt', 'try_stmt')
    def compound_stmt(self, p):
        return p[0]

    # ------------------------------------------------------ simple statements
    @_('testlist ASSIGN testlist')
    def assignment(self, p):
        target = _check_target(p[0])
        return Assign(target, p[2], **loc(target, p[2]))

    @_('testlist')
    def expr_stmt(self, p):
        return p.testlist

    @_('RETURN')
    def return_stmt(self, p):
        return Return(None, **loc(p.RETURN, p.RETURN))

    @_('RETURN testlist')
    def return_stmt(self, p):
        return Return(p.testlist, **loc(p.RETURN, p.testlist))

    @_('PASS')
    def pass_stmt(self, p):
        return Pass(**loc(p.PASS, p.PASS))

    @_('BREAK')
    def break_stmt(self, p):
        return Break(**loc(p.BREAK, p.BREAK))

    @_('CONTINUE')
    def continue_stmt(self, p):
        return Continue(**loc(p.CONTINUE, p.CONTINUE))

    @_('IMPORT alias_list')
    def import_stmt(self, p):
        return Import(None, p.alias_list, False, **loc(p.IMPORT, p.alias_list))

    @_('FROM dotted_name IMPORT alias_list')
    def import_stmt(self, p):
        return Import(p.dotted_name[0], p.alias_list, True,
                      **loc(p.FROM, p.alias_list))

    @_('alias')
    def alias_list(self, p):
        return [p.alias]

    @_('alias_list COMMA alias')
    def alias_list(self, p):
        return p.alias_list + [p.alias]

    @_('dotted_name')
    def alias(self, p):
        text, first, last = p.dotted_name
        return Alias(text, None, **loc(first, last))

    @_('dotted_name AS IDENTIFIER')
    def alias(self, p):
        text, first, _last = p.dotted_name
        return Alias(text, p.IDENTIFIER.value, **loc(first, p.IDENTIFIER))

    @_('IDENTIFIER')
    def dotted_name(self, p):
        return (p.IDENTIFIER.value, p.IDENTIFIER, p.IDENTIFIER)

    @_('dotted_name DOT IDENTIFIER')
    def dotted_name(self, p):
        text, first, _last = p.dotted_name
        return (text + "." + p.IDENTIFIER.value, first, p.IDENTIFIER)

    # -------------------------------------------------------------- blocks
    @_('NEWLINE INDENT stmt_list DEDENT')
    def block(self, p):
        return p.stmt_list

    @_('simple_stmt NEWLINE')
    def block(self, p):                      # one-line body:  if x: return 1
        return [p.simple_stmt]

    # ----------------------------------------------------- compound statements
    @_('DEF IDENTIFIER LPAREN RPAREN COLON block')
    def funcdef(self, p):
        return FunctionDef(p.IDENTIFIER.value, [], p.block,
                           **loc(p.DEF, p.block))

    @_('DEF IDENTIFIER LPAREN param_list RPAREN COLON block')
    def funcdef(self, p):
        return FunctionDef(p.IDENTIFIER.value, p.param_list, p.block,
                           **loc(p.DEF, p.block))

    @_('param')
    def param_list(self, p):
        return [p.param]

    @_('param_list COMMA param')
    def param_list(self, p):
        return p.param_list + [p.param]

    @_('param_list COMMA')
    def param_list(self, p):
        return p.param_list

    @_('IDENTIFIER')
    def param(self, p):
        return Parameter(p.IDENTIFIER.value, None,
                         **loc(p.IDENTIFIER, p.IDENTIFIER))

    @_('IDENTIFIER ASSIGN expr')
    def param(self, p):
        return Parameter(p.IDENTIFIER.value, p.expr,
                         **loc(p.IDENTIFIER, p.expr))

    @_('IF expr COLON block')
    def if_stmt(self, p):
        return If(p.expr, p.block, [], False, **loc(p.IF, p.block))

    @_('IF expr COLON block else_part')
    def if_stmt(self, p):
        return If(p.expr, p.block, p.else_part, False,
                  **loc(p.IF, p.else_part))

    @_('ELSE COLON block')
    def else_part(self, p):
        return p.block

    @_('ELIF expr COLON block')
    def else_part(self, p):
        return [If(p.expr, p.block, [], True, **loc(p.ELIF, p.block))]

    @_('ELIF expr COLON block else_part')
    def else_part(self, p):
        return [If(p.expr, p.block, p.else_part, True,
                   **loc(p.ELIF, p.else_part))]

    @_('FOR for_target IN testlist COLON block')
    def for_stmt(self, p):
        return For(p.for_target, p.testlist, p.block, **loc(p.FOR, p.block))

    @_('IDENTIFIER')
    def for_target(self, p):
        tok = p.IDENTIFIER
        return Name(tok.value, **loc(tok, tok))

    @_('for_target_list')
    def for_target(self, p):
        return p.for_target_list

    @_('IDENTIFIER COMMA IDENTIFIER')
    def for_target_list(self, p):
        a, b = p[0], p[2]
        return Tuple([Name(a.value, **loc(a, a)), Name(b.value, **loc(b, b))],
                     **loc(a, b))

    @_('for_target_list COMMA IDENTIFIER')
    def for_target_list(self, p):
        tup, tok = p[0], p[2]
        tup.elts.append(Name(tok.value, **loc(tok, tok)))
        tup.end_lineno, tup.end_col_offset = tok.end_lineno, tok.end_col
        return tup

    @_('WHILE expr COLON block')
    def while_stmt(self, p):
        return While(p.expr, p.block, **loc(p.WHILE, p.block))

    @_('WITH with_items COLON block')
    def with_stmt(self, p):
        return With(p.with_items, p.block, **loc(p.WITH, p.block))

    @_('with_item')
    def with_items(self, p):
        return [p.with_item]

    @_('with_items COMMA with_item')
    def with_items(self, p):
        return p.with_items + [p.with_item]

    @_('expr')
    def with_item(self, p):
        return WithItem(p.expr, None, **loc(p.expr, p.expr))

    @_('expr AS IDENTIFIER')
    def with_item(self, p):
        tok = p.IDENTIFIER
        var = Name(tok.value, **loc(tok, tok))
        return WithItem(p.expr, var, **loc(p.expr, tok))

    @_('TRY COLON block handlers')
    def try_stmt(self, p):
        return Try(p.block, p.handlers, [], **loc(p.TRY, p.handlers))

    @_('TRY COLON block handlers FINALLY COLON block')
    def try_stmt(self, p):
        return Try(p[2], p.handlers, p[6], **loc(p.TRY, p[6]))

    @_('TRY COLON block FINALLY COLON block')
    def try_stmt(self, p):
        return Try(p[2], [], p[5], **loc(p.TRY, p[5]))

    @_('handler')
    def handlers(self, p):
        return [p.handler]

    @_('handlers handler')
    def handlers(self, p):
        return p.handlers + [p.handler]

    @_('EXCEPT COLON block')
    def handler(self, p):
        return ExceptHandler(None, None, p.block, **loc(p.EXCEPT, p.block))

    @_('EXCEPT expr COLON block')
    def handler(self, p):
        return ExceptHandler(p.expr, None, p.block, **loc(p.EXCEPT, p.block))

    @_('EXCEPT expr AS IDENTIFIER COLON block')
    def handler(self, p):
        return ExceptHandler(p.expr, p.IDENTIFIER.value, p.block,
                             **loc(p.EXCEPT, p.block))

    # ---------------------------------------------------- expression lists
    # `a`, `a,`, `a, b`, `a, b,` ... a comma makes it a Tuple.
    @_('expr')
    def testlist(self, p):
        return p.expr

    @_('expr COMMA')
    def testlist(self, p):
        return Tuple([p.expr], **loc(p.expr, p.COMMA))

    @_('expr COMMA testlist_tail')
    def testlist(self, p):
        elts, last = p.testlist_tail
        return Tuple([p.expr] + elts, **loc(p.expr, last))

    @_('expr')
    def testlist_tail(self, p):
        return ([p.expr], p.expr)

    @_('expr COMMA')
    def testlist_tail(self, p):
        return ([p.expr], p.COMMA)

    @_('expr COMMA testlist_tail')
    def testlist_tail(self, p):
        elts, last = p.testlist_tail
        return ([p.expr] + elts, last)

    # ------------------------------------------------------------ expressions
    @_('expr OR and_test')
    def expr(self, p):
        return BoolOp("or", [p.expr, p.and_test], **loc(p.expr, p.and_test))

    @_('and_test')
    def expr(self, p):
        return p.and_test

    @_('and_test AND not_test')
    def and_test(self, p):
        return BoolOp("and", [p.and_test, p.not_test],
                      **loc(p.and_test, p.not_test))

    @_('not_test')
    def and_test(self, p):
        return p.not_test

    @_('NOT not_test')
    def not_test(self, p):
        return UnaryOp("not", p.not_test, **loc(p.NOT, p.not_test))

    @_('comparison')
    def not_test(self, p):
        return p.comparison

    @_('arith')
    def comparison(self, p):
        return p.arith

    @_('arith comp_chain')
    def comparison(self, p):
        ops = [op for op, _ in p.comp_chain]
        comparators = [c for _, c in p.comp_chain]
        return Compare(p.arith, ops, comparators,
                       **loc(p.arith, comparators[-1]))

    @_('comp_op arith')
    def comp_chain(self, p):
        return [(p.comp_op, p.arith)]

    @_('comp_chain comp_op arith')
    def comp_chain(self, p):
        return p.comp_chain + [(p.comp_op, p.arith)]

    @_('EQ', 'NE', 'LT', 'GT', 'LE', 'GE', 'IN', 'IS')
    def comp_op(self, p):
        return p[0].raw

    @_('NOT IN')
    def comp_op(self, p):
        return "not in"

    @_('IS NOT')
    def comp_op(self, p):
        return "is not"

    @_('arith PLUS term')
    def arith(self, p):
        return BinaryOp("+", p.arith, p.term, **loc(p.arith, p.term))

    @_('arith MINUS term')
    def arith(self, p):
        return BinaryOp("-", p.arith, p.term, **loc(p.arith, p.term))

    @_('term')
    def arith(self, p):
        return p.term

    @_('term MULTIPLY factor')
    def term(self, p):
        return BinaryOp("*", p.term, p.factor, **loc(p.term, p.factor))

    @_('term DIVIDE factor')
    def term(self, p):
        return BinaryOp("/", p.term, p.factor, **loc(p.term, p.factor))

    @_('term MODULO factor')
    def term(self, p):
        return BinaryOp("%", p.term, p.factor, **loc(p.term, p.factor))

    @_('factor')
    def term(self, p):
        return p.factor

    @_('MINUS factor')
    def factor(self, p):
        return UnaryOp("-", p.factor, **loc(p.MINUS, p.factor))

    @_('PLUS factor')
    def factor(self, p):
        return UnaryOp("+", p.factor, **loc(p.PLUS, p.factor))

    @_('postfix')
    def factor(self, p):
        return p.postfix

    # postfix: calls, attribute access, subscripts (all left-associative)
    @_('atom')
    def postfix(self, p):
        return p.atom

    @_('postfix LPAREN RPAREN')
    def postfix(self, p):
        return Call(p.postfix, [], [], **loc(p.postfix, p.RPAREN))

    @_('postfix LPAREN arglist RPAREN')
    def postfix(self, p):
        args = [a for a in p.arglist if not isinstance(a, Keyword)]
        keywords = [a for a in p.arglist if isinstance(a, Keyword)]
        return Call(p.postfix, args, keywords, **loc(p.postfix, p.RPAREN))

    @_('postfix DOT IDENTIFIER')
    def postfix(self, p):
        return Attribute(p.postfix, p.IDENTIFIER.value,
                         **loc(p.postfix, p.IDENTIFIER))

    @_('postfix LBRACKET expr RBRACKET')
    def postfix(self, p):
        return Subscript(p.postfix, p.expr, **loc(p.postfix, p.RBRACKET))

    @_('arg')
    def arglist(self, p):
        return [p.arg]

    @_('arglist COMMA arg')
    def arglist(self, p):
        return p.arglist + [p.arg]

    @_('arglist COMMA')
    def arglist(self, p):
        return p.arglist

    @_('expr')
    def arg(self, p):
        return p.expr

    @_('IDENTIFIER ASSIGN expr')
    def arg(self, p):
        return Keyword(p.IDENTIFIER.value, p.expr, **loc(p.IDENTIFIER, p.expr))

    # atoms
    @_('IDENTIFIER')
    def atom(self, p):
        tok = p.IDENTIFIER
        return Name(tok.value, **loc(tok, tok))

    @_('NUMBER')
    def atom(self, p):
        tok = p.NUMBER
        return Constant(tok.value, **loc(tok, tok))

    @_('STRING')
    def atom(self, p):
        tok = p.STRING
        return Constant(tok.value, **loc(tok, tok))

    @_('TRUE')
    def atom(self, p):
        return Constant(True, **loc(p.TRUE, p.TRUE))

    @_('FALSE')
    def atom(self, p):
        return Constant(False, **loc(p.FALSE, p.FALSE))

    @_('NONE')
    def atom(self, p):
        return Constant(None, **loc(p.NONE, p.NONE))

    @_('LPAREN testlist RPAREN')
    def atom(self, p):
        node = p.testlist
        if node.node_type == "Tuple":        # (a, b) -> the tuple includes the parens
            node.lineno, node.col_offset = p.LPAREN.lineno, p.LPAREN.col
            node.end_lineno, node.end_col_offset = p.RPAREN.end_lineno, p.RPAREN.end_col
        else:                                # (a + b): remember the outer span
            node._ostart = (p.LPAREN.lineno, p.LPAREN.col)
            node._oend = (p.RPAREN.end_lineno, p.RPAREN.end_col)
        return node

    @_('LPAREN RPAREN')
    def atom(self, p):
        return Tuple([], **loc(p.LPAREN, p.RPAREN))

    @_('LBRACKET RBRACKET')
    def atom(self, p):
        return List([], **loc(p.LBRACKET, p.RBRACKET))

    @_('LBRACKET list_items RBRACKET')
    def atom(self, p):
        return List(p.list_items, **loc(p.LBRACKET, p.RBRACKET))

    @_('expr')
    def list_items(self, p):
        return [p.expr]

    @_('list_items COMMA expr')
    def list_items(self, p):
        return p.list_items + [p.expr]

    @_('list_items COMMA')
    def list_items(self, p):
        return p.list_items

    # --------------------------------------------------------- error report
    def error(self, tok):
        """Called by SLY when no grammar action fits the next token."""
        last = getattr(self, "last_token", None)
        if tok is None or getattr(tok, "type", None) == "$end":
            tok = None
            if last is not None:
                line, col = last.end_lineno, last.end_col
            else:
                line, col = 1, 0
        else:
            line, col = tok.value.lineno, tok.value.col
        shown = tok.value if tok is not None else None
        try:
            state = self.statestack[-1]
            expected = describe_expected(self._lrtable.lr_action[state].keys())
        except Exception:                    # SLY internals differ: just omit
            expected = None
        raise SourceSyntaxError("Syntax error", line, col,
                                unexpected=describe_unexpected(shown),
                                expected=expected)


def parse_tokens(tokens, source=""):
    """Run the SLY parser over a token list (from lexer.tokenize)."""
    parser = PythonParser()
    parser.last_token = tokens[-1] if tokens else None
    return parser.parse(iter([_ParserToken(t) for t in tokens]))


def parse_source(source):
    """Source text -> Program AST. Raises SourceError subclasses on bad input."""
    source = normalize_source(source)
    lines = LineIndex(source)
    end_line, end_col = lines.locate(len(source))
    tokens = tokenize(source)
    if not tokens:                           # empty file or only comments
        return Program([], lineno=1, col_offset=0,
                       end_lineno=end_line, end_col_offset=end_col)
    program = parse_tokens(tokens, source)
    program.lineno, program.col_offset = 1, 0
    program.end_lineno, program.end_col_offset = end_line, end_col
    return program
