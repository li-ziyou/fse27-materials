from __future__ import annotations

from .model import Node, InvalidTreeError, NodeNotFoundError


def attach(parent: Node, name: str, child: Node) -> None:
    if not name or name in (".", "..") or "/" in name:
        raise InvalidTreeError(f"Invalid child name: '{name}'")

    if name in parent._children:
        raise InvalidTreeError(f"Child name '{name}' already exists")

    if child.parent is not None:
        # If the child is already attached, detach it first.
        # This handles moving subtrees.
        if child.parent is parent and child.name == name:
            # Attaching to itself with the same name, do nothing.
            return
        detach(child.parent, child.name)

    # Check for self-links and ancestor cycles before attaching
    if child is parent:
        raise InvalidTreeError("Cannot attach a node to itself")
    current = parent
    while current is not None:
        if current is child:
            raise InvalidTreeError("Cannot attach a node to its descendant")
        current = current.parent

    child._parent = parent
    child._name = name
    parent._children[name] = child


def detach(parent: Node, name: str) -> Node:
    if name not in parent._children:
        raise NodeNotFoundError(f"Child '{name}' not found")

    child = parent._children.pop(name)
    child._parent = None
    child._name = None
    return child


def replace(parent: Node, name: str, child: Node) -> Node:
    if name not in parent._children:
        raise NodeNotFoundError(f"Child '{name}' not found")

    old_child = parent._children[name]

    if child.parent is not None:
        if child.parent is parent and child.name == name:
            # Replacing with itself, do nothing.
            return old_child
        detach(child.parent, child.name)

    # Check for self-links and ancestor cycles before replacing
    if child is parent:
        raise InvalidTreeError("Cannot replace with a node that is itself")
    current = parent
    while current is not None:
        if current is child:
            raise InvalidTreeError("Cannot replace with a node that is its descendant")
        current = current.parent

    child._parent = parent
    child._name = name
    parent._children[name] = child
    old_child._parent = None
    old_child._name = None
    return old_child


def orphan(node: Node) -> Node:
    if node.parent is None:
        # Already orphaned
        return node

    parent = node.parent
    name = node.name
    detach(parent, name)  # detach will clear node's parent and name
    return node
