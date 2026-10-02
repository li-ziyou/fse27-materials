from __future__ import annotations

from .model import Node, InvalidTreeError, NodeNotFoundError


def attach(parent: Node, name: str, child: Node) -> None:
    # TN-A1: Accept non-empty child name other than '.' or '..' with no '/'.
    if not name or name in (".", "..") or "/" in name:
        raise ValueError("Invalid child name.")

    # TN-A1: Reject occupied name unless the operation is 'replace'.
    if name in parent._children and not isinstance(child, Node):  # Assuming child is always a Node here
        raise ValueError(f"Name '{name}' is already occupied.")

    # TN-A3: Reject self-links and ancestor cycles.
    current = parent
    while current:
        if current is child:
            raise InvalidTreeError("Cannot attach a node to itself or its descendant.")
        current = current.parent
    
    # If child is already attached, detach it first.
    if child.parent and child.name:
        detach(child.parent, child.name)

    # Attach the child.
    child._parent = parent
    child._name = name
    parent._children[name] = child


def detach(parent: Node, name: str) -> Node:
    if name not in parent._children:
        raise NodeNotFoundError(f"Child '{name}' not found.")

    child = parent._children[name]
    del parent._children[name]
    child._parent = None
    child._name = None
    return child


def replace(parent: Node, name: str, child: Node) -> Node:
    # TN-A1: Accept non-empty child name other than '.' or '..' with no '/'.
    if not name or name in (".", "..") or "/" in name:
        raise ValueError("Invalid child name.")

    if name not in parent._children:
        raise NodeNotFoundError(f"Child '{name}' not found for replacement.")

    # TN-A3: Reject self-links and ancestor cycles.
    current = parent
    while current:
        if current is child:
            raise InvalidTreeError("Cannot replace with a node that is itself or its ancestor.")
        current = current.parent

    # If child is already attached, detach it first.
    if child.parent and child.name:
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
        raise InvalidTreeError("Node is already orphaned.")
    
    parent = node.parent
    name = node.name
    
    if parent and name:
        detach(parent, name)
        
    return node
