from __future__ import annotations

from .model import Node, InvalidTreeError, NodeNotFoundError


def _validate_name(name: str) -> None:
    if not name or name in (".", "..") or "/" in name:
        raise InvalidTreeError(
            "Child name must be non-empty, not '.' or '..', and contain no '/'"
        )


def attach(parent: Node, name: str, child: Node) -> None:
    _validate_name(name)

    # TN-A3: Check for self-links
    if child is parent:
        raise InvalidTreeError("Cannot attach a node to itself.")

    # TN-A3: Check for ancestor cycles
    current = parent
    while current is not None:
        if current is child:
            raise InvalidTreeError("Cannot attach a node to one of its descendants.")
        current = current._parent

    if name in parent._children and parent._children[name] is not child:
        raise InvalidTreeError(f"Name '{name}' is already occupied.")

    # If the child is already attached elsewhere, detach it first.
    if child._parent is not None and child._parent is not parent:
        # TN-A2: Attaching an already attached node moves its complete subtree.
        # Detach it from its old parent.
        detach(child._parent, child._name)

    # If the child is already a child of the parent (moving within the same parent)
    if child._parent is parent and child._name == name:
        return # No change needed

    child._parent = parent
    child._name = name
    parent._children[name] = child


def detach(parent: Node, name: str) -> Node:
    if name not in parent._children:
        raise NodeNotFoundError(f"Child '{name}' not found.")

    child = parent._children.pop(name)
    child._parent = None
    child._name = None
    return child


def replace(parent: Node, name: str, child: Node) -> Node:
    _validate_name(name)

    # TN-A3: Check for self-links
    if child is parent:
        raise InvalidTreeError("Cannot replace a node with itself.")

    # TN-A3: Check for ancestor cycles
    current = parent
    while current is not None:
        if current is child:
            raise InvalidTreeError("Cannot replace a node with one of its descendants.")
        current = current._parent

    if name not in parent._children:
        raise NodeNotFoundError(f"Child '{name}' not found for replacement.")

    old_child = parent._children[name]

    # If the child is already attached elsewhere, detach it first.
    if child._parent is not None and child._parent is not parent:
        # TN-A2: Replacing a node moves the new child's subtree.
        detach(child._parent, child._name)

    child._parent = parent
    child._name = name
    parent._children[name] = child

    # Clear the old child's parent and name
    old_child._parent = None
    old_child._name = None
    return old_child


def orphan(node: Node) -> Node:
    if node._parent is None or node._name is None:
        # This node is already orphaned or is the root.
        return node

    parent = node._parent
    name = node._name
    detach(parent, name)
    return node
