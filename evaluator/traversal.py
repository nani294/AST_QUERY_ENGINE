"""Generic traversal of the custom AST.

Walks the tree once (iteratively, in source order) and records, for every
node, its parent and children. From that the evaluator can ask for:

    parent_of(n)        the node directly above n
    ancestors_of(n)     [parent, grandparent, ..., Program]   (nearest first)
    children_of(n)      direct children
    descendants_of(n)   every node below n, in source order

Example:  Program > FunctionDef > For > Call
    for the Call:  parent = For,  ancestors = [For, FunctionDef, Program]
"""


class Traversal:
    def __init__(self, root):
        self.root = root
        self.nodes = []             # every node, pre-order (= source order)
        self._parent = {}
        self._children = {}
        self._build()

    def _build(self):
        self._parent[self.root] = None
        stack = [self.root]
        while stack:
            node = stack.pop()
            self.nodes.append(node)
            kids = node.children()
            self._children[node] = kids
            for kid in kids:
                self._parent[kid] = node
            stack.extend(reversed(kids))      # reversed -> left-to-right order

    def parent_of(self, node):
        return self._parent.get(node)

    def children_of(self, node):
        return list(self._children.get(node, []))

    def ancestors_of(self, node):
        out = []
        cur = self._parent.get(node)
        while cur is not None:
            out.append(cur)
            cur = self._parent.get(cur)
        return out

    def descendants_of(self, node):
        out = []
        stack = list(reversed(self._children.get(node, [])))
        while stack:
            cur = stack.pop()
            out.append(cur)
            stack.extend(reversed(self._children.get(cur, [])))
        return out

    def depth_of(self, node):
        return len(self.ancestors_of(node))
