from __future__ import annotations

from .model import Node, InvalidTreeError, NodeNotFoundError


def attach(parent: Node, name: str, child: Node) -> None:
    # TN-A1: Validates name and checks for existing child.
    if not name or name in (".", "..") or "/" in name:
        raise InvalidTreeError("Invalid child name.")
    if name in parent._children and name != child.name:
        raise InvalidTreeError(f"Name '{name}' is already occupied.")

    # TN-A3: Check for self-links and ancestor cycles.
    if child is parent:
        raise InvalidTreeError("Cannot attach a node to itself.")
    current = parent
    while current:
        if child is current:
            raise InvalidTreeError("Cannot attach a node to its own ancestor.")
        current = current.parent

    # If the child is already attached elsewhere, detach it first.
    if child.parent is not None and child.parent != parent:
        detach(child.parent, child.name)

    # Attach the child.
    child._parent = parent
    child._name = name
    parent._children[name] = child


def detach(parent: Node, name: str) -> Node:
    # TN-A4: Reports missing children.
    if name not in parent._children:
        raise NodeNotFoundError(f"Child '{name}' not found.")

    child = parent._children.pop(name)
    child._parent = None
    child._name = None
    return child


def replace(parent: Node, name: str, child: Node) -> Node:
    # TN-A1: Validates name and checks for existing child.
    if not name or name in (".", "..") or "/" in name:
        raise InvalidTreeError("Invalid child name.")

    # TN-A3: Check for self-links and ancestor cycles.
    if child is parent:
        raise InvalidTreeError("Cannot replace a node with itself.")
    current = parent
    while current:
        if child is current:
            raise InvalidTreeError("Cannot replace a node with its own ancestor.")
        current = current.parent

    # If the child is already attached elsewhere, detach it first.
    if child.parent is not None and child.parent != parent:
        # Ensure we are not trying to replace a node with a child of itself
        if child.parent == child:
            raise InvalidTreeError("Cannot replace a node with itself.")
        detach(child.parent, child.name)

    # Detach the old child if it exists.
    old_child = None
    if name in parent._children:
        old_child = parent._children.pop(name)
        old_child._parent = None
        old_child._name = None

    # Attach the new child.
    child._parent = parent
    child._name = name
    parent._children[name] = child

    return old_child if old_child is not None else child


def orphan(node: Node) -> Node:
    if node.parent is None:
        return node  # Already orphaned

    parent = node.parent
    name = node.name
    if name is None:
        # This should ideally not happen if the node is attached
        raise InvalidTreeError("Node to orphan has no name.")

    # Detach from parent
    parent._children.pop(name)
    node._parent = None
    node._name = None
    return node
