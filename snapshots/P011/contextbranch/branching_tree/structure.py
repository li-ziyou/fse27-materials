from __future__ import annotations

from .model import Node, InvalidTreeError, NodeNotFoundError


def attach(parent: Node, name: str, child: Node) -> None:
    if not name or name in (".", "..") or "/" in name:
        raise InvalidTreeError(f"Invalid child name: '{name}'")

    if name in parent._children:
        raise InvalidTreeError(f"Name '{name}' is already occupied.")

    if child.parent is not None and child.parent is not parent:
        # Detach from old parent if it exists and is different
        detach(child.parent, child.name)

    if child.parent is parent and child.name == name:
        # Already attached correctly, do nothing
        return

    # Check for self-links and ancestor cycles
    current = parent
    while current is not None:
        if current is child:
            raise InvalidTreeError("Cannot attach a node to itself or one of its ancestors.")
        current = current.parent

    child._parent = parent
    child._name = name
    parent._children[name] = child


def detach(parent: Node, name: str) -> Node:
    if name not in parent._children:
        raise NodeNotFoundError(f"Child with name '{name}' not found.")
    
    child = parent._children.pop(name)
    child._parent = None
    child._name = None
    return child


def replace(parent: Node, name: str, child: Node) -> Node:
    if name not in parent._children:
        raise NodeNotFoundError(f"Child with name '{name}' not found.")
    
    old_child = parent._children[name]

    # Detach the old child
    parent._children.pop(name)
    old_child._parent = None
    old_child._name = None

    # Attach the new child
    attach(parent, name, child)
    
    return old_child


def orphan(node: Node) -> Node:
    if node.parent is None:
        raise InvalidTreeError("Node is already orphaned.")
    
    parent = node.parent
    name = node.name
    
    # Detach from parent
    parent._children.pop(name)
    node._parent = None
    node._name = None
    
    return node
