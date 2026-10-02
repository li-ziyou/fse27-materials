from __future__ import annotations

from .model import Node, InvalidTreeError, NodeNotFoundError


def attach(parent: Node, name: str, child: Node) -> None:
    if not name or name in (".", ".."):
        raise InvalidTreeError(f"Invalid child name: {name}")

    if "/" in name:
        raise InvalidTreeError(f"Child name cannot contain '/': {name}")

    if name in parent._children:
        raise InvalidTreeError(f"Child name '{name}' already exists")

    if child._parent is not None or child._name is not None:
        # If the child is already attached, detach it first.
        # This handles moving a node.
        if child._parent is not None and child._name is not None:
            try:
                detach(child._parent, child._name)
            except NodeNotFoundError:
                # This should ideally not happen if the child's parent and name are set
                pass

    # Check for self-links and ancestor cycles
    current = parent
    while current is not None:
        if current is child:
            raise InvalidTreeError("Cannot attach a node to itself or one of its descendants")
        current = current._parent

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
    detach(parent, name)

    # Attach the new child
    attach(parent, name, child)

    return old_child


def orphan(node: Node) -> Node:
    if node.parent is None or node.name is None:
        # Node is already detached or is the root and cannot be orphaned further
        return node

    parent = node.parent
    name = node.name

    # Detach the node from its parent
    detach(parent, name)

    return node
