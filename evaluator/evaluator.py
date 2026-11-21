"""Query evaluation: Query AST + Program AST -> matches.

For every node of the program we ask "does this node satisfy the query?".
Evaluation is a generator of *binding environments*: each yielded dict is one
way the query can be true for the node, with its metavariable bindings. An
empty result means "no match".

    NodeMatch   node has the right type and the predicate holds
    Predicate   resolve the attribute path and compare (binds $X on first use)
    And         every environment of the left feeds into the right
    Or          environments of either side
    Not         true (no new bindings) when the operand yields nothing
    Parent / Ancestor / Descendant
                the operand must hold for the parent / some ancestor / some descendant
"""
from query_language.query_ast import (And, Ancestor, Descendant, Literal,
                                      MetaVariable, NodeMatch, Not, Or, Parent,
                                      Predicate)
from source_parser.ast_nodes import ASTNode
from .matcher import Match, compare, extract_snippet, resolve_path
from .traversal import Traversal


class QueryEvaluator:
    def __init__(self, program, source=""):
        self.program = program
        self.source = source
        self.traversal = Traversal(program)

    def evaluate(self, query):
        matches = []
        for node in self.traversal.nodes:
            env = next(self._eval(query, node, {}), None)
            if env is not None:
                matches.append(self._make_match(node, env))
        return matches

    # ------------------------------------------------------------------
    def _make_match(self, node, env):
        return Match(node=node, node_type=node.node_type, line=node.lineno,
                     column=node.col_offset + 1, end_line=node.end_lineno,
                     end_column=node.end_col_offset + 1,
                     snippet=extract_snippet(self.source, node) if self.source else "",
                     bindings=dict(env))

    def _eval(self, q, node, env):
        t = self.traversal
        if isinstance(q, NodeMatch):
            if node.node_type != q.node_type:
                return
            if q.predicate is None:
                yield env
            else:
                yield from self._eval(q.predicate, node, env)
        elif isinstance(q, Predicate):
            yield from self._eval_predicate(q, node, env)
        elif isinstance(q, And):
            for env1 in self._eval(q.left, node, env):
                yield from self._eval(q.right, node, env1)
        elif isinstance(q, Or):
            yield from self._eval(q.left, node, env)
            yield from self._eval(q.right, node, env)
        elif isinstance(q, Not):
            if next(self._eval(q.operand, node, env), None) is None:
                yield env
        elif isinstance(q, Parent):
            parent = t.parent_of(node)
            if parent is not None:
                yield from self._eval(q.operand, parent, env)
        elif isinstance(q, Ancestor):
            for anc in t.ancestors_of(node):
                yield from self._eval(q.operand, anc, env)
        elif isinstance(q, Descendant):
            for desc in t.descendants_of(node):
                yield from self._eval(q.operand, desc, env)
        else:
            raise TypeError(f"Cannot evaluate query node {q!r}")

    def _eval_predicate(self, pred, node, env):
        found, actual = resolve_path(node, pred.path)
        if not found:
            return
        rhs = pred.value
        if isinstance(rhs, MetaVariable):
            if isinstance(actual, ASTNode):          # bind the node's source text
                from .matcher import extract_snippet as snip
                actual = snip(self.source, actual)
            if rhs.name in env:
                if compare("==", actual, env[rhs.name]):
                    yield env
            else:
                new_env = dict(env)
                new_env[rhs.name] = actual
                yield new_env
        elif isinstance(rhs, Literal):
            if compare(pred.op, actual, rhs.value):
                yield env
