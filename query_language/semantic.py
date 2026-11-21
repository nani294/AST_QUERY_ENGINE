"""Semantic analysis: reject queries that parse but make no sense.

The parser only checks grammar. This stage checks meaning, against the
schema of the source AST (source_parser/ast_nodes.py):

  * node types exist                      (UnknownNode -> error + suggestion)
  * attribute paths exist for that type   (Call(colour == "red") -> error)
  * operators fit the attribute's kind    (num_params < "x" -> error)
  * metavariables are used legally        ($X only with ==)
  * relationships can ever be true        (Name descendant For -> error)
  * the query selects something           (NOT ancestor(With) alone -> error)
"""
import difflib

from source_parser.ast_nodes import (LEAF_TYPES, NODE_CLASSES, attribute_kind,
                                     attributes_of)
from .errors import QuerySemanticError, SemanticIssue
from .query_ast import (And, Ancestor, Descendant, Literal, MetaVariable,
                        NodeMatch, Not, Or, Parent, Predicate)

ORDERING = {"<", ">", "<=", ">="}


def _literal_kind(value):
    if isinstance(value, bool):
        return "bool"
    if value is None:
        return "None"
    if isinstance(value, (int, float)):
        return "num"
    return "str"


def _label(kind):
    return "node" if isinstance(kind, tuple) else kind


class SemanticAnalyzer:
    def __init__(self):
        self.issues = []

    # ------------------------------------------------------------- entry
    def analyze(self, query):
        self.issues = []
        self._visit(query, None)
        self._check_conjunctions(query)
        if not self._selects_node(query):
            self._error("A query must select a node type (such as Call) "
                        "outside of NOT; relationships alone select nothing",
                        query,
                        "Example: Call AND NOT ancestor(With)")
        if self.issues:
            raise QuerySemanticError(self.issues)
        return query

    def _error(self, message, node, hint=None):
        self.issues.append(SemanticIssue(message, getattr(node, "lineno", None),
                                         getattr(node, "col", None), hint))

    # ------------------------------------------------------------ walking
    def _visit(self, q, node_type):
        """node_type is set while inside the ( ... ) of a NodeMatch."""
        if isinstance(q, NodeMatch):
            known = q.node_type in NODE_CLASSES
            if not known:
                close = difflib.get_close_matches(q.node_type, NODE_CLASSES, n=1)
                hint = f"Did you mean '{close[0]}'?" if close else \
                    "Known node types: " + ", ".join(sorted(NODE_CLASSES))
                self._error(f"Unknown AST node type '{q.node_type}'", q, hint)
            if q.predicate is not None:
                self._visit(q.predicate, q.node_type if known else "?")
        elif isinstance(q, Predicate):
            self._check_predicate(q, node_type)
        elif isinstance(q, (And, Or)):
            self._visit(q.left, node_type)
            self._visit(q.right, node_type)
        elif isinstance(q, Not):
            self._visit(q.operand, node_type)
        elif isinstance(q, (Parent, Ancestor, Descendant)):
            self._visit(q.operand, None)
            if isinstance(q, Descendant) and isinstance(q.operand, NodeMatch) \
                    and q.operand.node_type == "Program":
                self._error("'Program' is the root and can never be a descendant",
                            q)

    # --------------------------------------------------------- predicates
    def _resolve(self, pred, start_type):
        """Follow the attribute path; return the set of possible final kinds."""
        types = [start_type]
        for i, seg in enumerate(pred.path):
            found = []
            for t in types:
                kind = attribute_kind(t, seg)
                if kind is not None:
                    found.append(kind)
            if not found:
                dotted = ".".join(pred.path[:i + 1])
                if i == 0:
                    names = sorted(attributes_of(start_type))
                    close = difflib.get_close_matches(seg, names, n=1)
                    hint = (f"Did you mean '{close[0]}'? " if close else "") + \
                        f"Available attributes: " + ", ".join(names)
                    self._error(f"Node type '{start_type}' has no attribute '{seg}'",
                                pred, hint)
                else:
                    self._error(f"Invalid attribute path '{dotted}': none of "
                                f"{', '.join(types)} has attribute '{seg}'", pred)
                return None
            if i < len(pred.path) - 1:
                nodes = [k for k in found if isinstance(k, tuple)]
                if not nodes:
                    self._error(f"Cannot read '.{pred.path[i + 1]}' of "
                                f"'{'.'.join(pred.path[:i + 1])}': it is not a node",
                                pred)
                    return None
                types = sorted({t for k in nodes for t in k[1]})
            else:
                return found

    def _check_predicate(self, pred, node_type):
        if node_type in (None, "?"):
            return
        kinds = self._resolve(pred, node_type)
        if kinds is None:
            return
        labels = {_label(k) for k in kinds}
        dotted = ".".join(pred.path)
        value = pred.value
        if isinstance(value, MetaVariable):
            if pred.op != "==":
                self._error(f"Metavariable {value.name} can only be used with "
                            f"'==', not '{pred.op}'", pred,
                            "A metavariable is bound by '==' (e.g. func.name == $X)")
            return        # a node-valued attribute binds as its source text
        lit = _literal_kind(value.value)
        if pred.op in ORDERING:
            ok = "any" in labels or \
                (lit == "num" and "int" in labels) or (lit == "str" and "str" in labels)
            if not ok:
                self._error(f"Operator '{pred.op}' cannot compare "
                            f"'{dotted}' ({'/'.join(sorted(labels))}) "
                            f"with a {lit} value", pred)
            return
        compatible = (
            "any" in labels
            or (lit == "str" and "str" in labels)
            or (lit == "num" and "int" in labels)
            or (lit == "bool" and "bool" in labels)
            or (lit == "None" and labels & {"node", "str", "any"})
        )
        if not compatible:
            self._error(f"Cannot compare '{dotted}' ({'/'.join(sorted(labels))}) "
                        f"with a {lit} value", pred)

    # ----------------------------------------------------- query structure
    def _selects_node(self, q):
        if isinstance(q, NodeMatch):
            return True
        if isinstance(q, And):
            return self._selects_node(q.left) or self._selects_node(q.right)
        if isinstance(q, Or):
            return self._selects_node(q.left) and self._selects_node(q.right)
        return False

    @staticmethod
    def _conjuncts(q):
        if isinstance(q, And):
            return SemanticAnalyzer._conjuncts(q.left) + SemanticAnalyzer._conjuncts(q.right)
        return [q]

    def _check_conjunctions(self, q):
        """Look for relationships that can never be true for a node type."""
        if isinstance(q, (And, Or, Not, Parent, Ancestor, Descendant)):
            for kid in q.children():
                self._check_conjunctions(kid)
        elif isinstance(q, NodeMatch) and q.predicate is not None:
            self._check_conjunctions(q.predicate)
        if not isinstance(q, And):
            return
        parts = self._conjuncts(q)
        types = [p.node_type for p in parts if isinstance(p, NodeMatch)]
        for part in parts:
            if isinstance(part, Descendant):
                for t in types:
                    if t in LEAF_TYPES:
                        self._error(f"'{t}' nodes never have descendants, so "
                                    "'descendant(...)' can never match", part)
            if isinstance(part, (Parent, Ancestor)) and "Program" in types:
                kind = type(part).__name__.lower()
                self._error(f"'Program' is the root and has no {kind}, so "
                            f"'{kind}(...)' can never match", part)


def analyze(query):
    return SemanticAnalyzer().analyze(query)
