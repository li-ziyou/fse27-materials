from __future__ import annotations

from .model import Node, InvalidTreeError, NodeNotFoundError


def attach(parent: Node, name: str, child: Node) -> None:
    if name in (".", ".."):
        raise ValueError("Child name cannot be '.' or '..'")
    if "/" in name:
        raise ValueError("Child name cannot contain '/'")
    if not name:
        raise ValueError("Child name cannot be empty")

    if name in parent._children:
        raise NodeNotFoundError(f"Child '{name}' already exists")

    if child.parent is not None or child.name is not None:
        # If the child is already attached elsewhere, detach it first.
        # This handles moving subtrees.
        if child.parent:
            detach(child.parent, child.name) # type: ignore

    # Check for self-links and ancestor cycles
    current = parent
    while current is not None:
        if current is child:
            raise InvalidTreeError("Cannot attach a node to itself or one of its descendants")
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

    # Detach the old child
    old_child._parent = None
    old_child._name = None

    # Check for self-links and ancestor cycles for the new child
    current = parent
    while current is not None:
        if current is child:
            raise InvalidTreeError("Cannot replace with a node that is itself or one of its descendants")
        current = current.parent

    # Attach the new child
    child._parent = parent
    child._name = name
    parent._children[name] = child

    return old_child


def orphan(node: Node) -> Node:
    if node.parent is None:
        raise InvalidTreeError("Cannot orphan the root node")
    
    detached_node = detach(node.parent, node.name) # type: ignore
    return detached_node
