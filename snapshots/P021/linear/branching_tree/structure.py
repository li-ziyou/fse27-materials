from __future__ import annotations

from .model import Node, NodeNotFoundError, InvalidTreeError


def attach(parent: Node, name: str, child: Node) -> None:
    if not name or name in (".", ".."):
        raise InvalidTreeError("Invalid child name.")
    if "/" in name:
        raise InvalidTreeError("Child name cannot contain '/'.")
    if name in parent._children:
        raise InvalidTreeError(f"Name '{name}' is already occupied.")

    # Check for self-link or ancestor cycle before attaching
    if child is parent or child in parent.ancestors:
        raise InvalidTreeError("Cannot attach node to itself or an ancestor.")

    if child.parent is not None or child.name is not None:
        # If child is already attached, detach it first.
        # This handles moving subtrees.
        if child.parent:
            # The check for self-link/ancestor cycle is done above before detaching
            # to ensure atomicity. If the child is an ancestor of the parent,
            # detaching it would be problematic.
            detach(child.parent, child.name)
        # If child.parent is None, it means the child is already orphaned,
        # so no detachment is needed.

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
    if name not in parent._children:
        raise NodeNotFoundError(f"Child '{name}' not found.")
    
    old_child = parent._children[name]

    # Check for self-link or ancestor cycle before attaching
    if child is parent or child in parent.ancestors:
        raise InvalidTreeError("Cannot replace node with itself or an ancestor.")

    if child.parent is not None or child.name is not None:
        # If child is already attached, detach it first.
        # This handles moving subtrees.
        if child.parent:
            # The check for self-link/ancestor cycle is done above before detaching
            # to ensure atomicity.
            detach(child.parent, child.name)
        # If child.parent is None, it means the child is already orphaned,
        # so no detachment is needed.

    child._parent = parent
    child._name = name
    parent._children[name] = child

    old_child._parent = None
    old_child._name = None
    return old_child


def orphan(node: Node) -> Node:
    if node.parent is None:
        # Already orphaned or is the root
        return node

    parent = node.parent
    name = node.name
    
    # Detach from parent
    if name in parent._children:
        del parent._children[name]

    node._parent = None
    node._name = None
    return node
