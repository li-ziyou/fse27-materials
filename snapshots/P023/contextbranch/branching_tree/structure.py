from __future__ import annotations

from .model import Node, InvalidTreeError, NodeNotFoundError


def attach(parent: Node, name: str, child: Node) -> None:
    if not name or name in (".", "..") or "/" in name:
        raise InvalidTreeError(f"Invalid child name: {name}")

    if name in parent._children:
        raise InvalidTreeError(f"Name '{name}' is already occupied in parent '{parent._name}'")

    # Check for self-links and ancestor cycles
    current = parent
    while current:
        if current is child:
            raise InvalidTreeError("Cannot attach a node to itself or one of its descendants")
        current = current.parent
    
    # If child is already attached, detach it first
    if child.parent and child.name:
        detach(child.parent, child.name)

    child._parent = parent
    child._name = name
    parent._children[name] = child


def detach(parent: Node, name: str) -> Node:
    if name not in parent._children:
        raise NodeNotFoundError(f"Child '{name}' not found in parent '{parent._name}'")

    child_to_detach = parent._children[name]
    del parent._children[name]
    child_to_detach._parent = None
    child_to_detach._name = None
    return child_to_detach


def replace(parent: Node, name: str, child: Node) -> Node:
    # Detach the existing child first
    detached_child = detach(parent, name)

    # Attach the new child
    attach(parent, name, child)

    # The detached child should have its parent and name cleared by detach
    # and the new child's parent and name should be set by attach.
    # Return the detached child as per TN-A4.
    return detached_child


def orphan(node: Node) -> Node:
    raise NotImplementedError
