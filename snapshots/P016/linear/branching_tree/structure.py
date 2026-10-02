from __future__ import annotations

from .model import Node, InvalidTreeError, NodeNotFoundError


def attach(parent: Node, name: str, child: Node) -> None:
    if not name or name in (".", "..") or "/" in name:
        raise InvalidTreeError("Invalid child name")
    if name in parent._children:
        raise InvalidTreeError(f"Name '{name}' already exists under parent.")

    # TN-A3: structural operations reject self-links and ancestor cycles without partially changing either tree.
    if child.parent is not None and child is parent:
        raise InvalidTreeError("Cannot attach a node to itself.")
    current = parent
    while current is not None:
        if current is child:
            raise InvalidTreeError("Cannot attach a node to one of its descendants.")
        current = current.parent

    # TN-A2: attaching an already attached node moves its complete subtree.
    if child.parent is not None and child.parent is not parent:
        # Detach from old parent if it exists and is not the same as the new parent
        if child.parent._children.get(child.name) is child:
            detach(child.parent, child.name)

    child._parent = parent
    child._name = name
    parent._children[name] = child


def detach(parent: Node, name: str) -> Node:
    if name not in parent._children:
        raise NodeNotFoundError(f"Child '{name}' not found under parent.")

    child = parent._children.pop(name)
    child._parent = None
    child._name = None
    return child


def replace(parent: Node, name: str, child: Node) -> Node:
    if name not in parent._children:
        raise NodeNotFoundError(f"Child '{name}' not found under parent for replacement.")

    # TN-A2: attaching an already attached node moves its complete subtree.
    if child.parent is not None and child.parent is not parent:
        # Detach from old parent if it exists and is not the same as the new parent
        if child.parent._children.get(child.name) is child:
            detach(child.parent, child.name)

    old_child = parent._children[name]
    child._parent = parent
    child._name = name
    parent._children[name] = child
    old_child._parent = None
    old_child._name = None
    return old_child


def orphan(node: Node) -> Node:
    if node.parent is None:
        # Cannot orphan a root node if it has children.
        # If it's a root with no children, it's already orphaned.
        if node._children:
            raise InvalidTreeError("Cannot orphan a root node with children.")
        return node

    parent = node.parent
    if parent._children.get(node.name) is node:
        detach(parent, node.name)
    return node