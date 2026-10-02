from __future__ import annotations

from .model import InvalidTreeError, Node, NodeNotFoundError

def _validate_child_name(name: str) -> None:
    if not name or "/" in name or name in (".", ".."):
        raise InvalidTreeError(f"Invalid child name: {name!r}")

def _check_cycle(potential_parent: Node, child: Node) -> None:
    """Check if attaching child to potential_parent would create a cycle."""
    if child is potential_parent:
        raise InvalidTreeError("Cannot attach a node to itself.")
    current = potential_parent
    while current:
        if current is child:
            raise InvalidTreeError("Cannot attach a node to one of its descendants.")
        current = current.parent


def attach(parent: Node, name: str, child: Node) -> None:
    _validate_child_name(name)
    _check_cycle(parent, child)

    if name in parent._children:
        raise InvalidTreeError(f"Name '{name}' already exists under parent.")

    if child.parent is not None or child.name is not None:
        # If the child is already attached, detach it first.
        # This handles moving subtrees.
        if child.parent is not None and child.name is not None:
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
    _validate_child_name(name)
    _check_cycle(parent, child)

    if name not in parent._children:
        raise NodeNotFoundError(f"Child '{name}' not found for replacement.")

    old_child = parent._children[name]

    if child.parent is not None or child.name is not None:
        # If the child is already attached, detach it first.
        if child.parent is not None and child.name is not None:
            detach(child.parent, child.name)

    child._parent = parent
    child._name = name
    parent._children[name] = child

    # Clear metadata of the old child
    old_child._parent = None
    old_child._name = None

    return old_child


def orphan(node: Node) -> Node:
    if node.parent is None or node.name is None:
        # Node is already orphaned or is the root
        return node

    parent = node.parent
    name = node.name
    detach(parent, name)
    return node
