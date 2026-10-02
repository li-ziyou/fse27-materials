from __future__ import annotations

from .model import Node, InvalidTreeError, NodeNotFoundError


def attach(parent: Node, name: str, child: Node) -> None:
    # TN-A1: Validate name
    if not name or name in (".", "..") or "/" in name:
        raise InvalidTreeError(f"Invalid child name: '{name}'")

    # TN-A1: Reject occupied name unless replacing
    if name in parent._children and child._parent is not parent:
        raise InvalidTreeError(f"Name '{name}' is already occupied")

    # TN-A3: Reject self-links
    if child is parent:
        raise InvalidTreeError("Cannot attach a node to itself")

    # TN-A3: Reject ancestor cycles
    current = parent
    while current is not None:
        if child is current:
            raise InvalidTreeError("Cannot attach a node to one of its descendants")
        current = current.parent

    # TN-A2: Attaching an already attached node moves its complete subtree.
    # If child is already attached elsewhere, detach it first.
    if child.parent is not None and child.parent is not parent:
        detach(child.parent, child.name)

    # Perform the attachment
    child._parent = parent
    child._name = name
    parent._children[name] = child


def detach(parent: Node, name: str) -> Node:
    # TN-A4: Report missing children
    if name not in parent._children:
        raise NodeNotFoundError(f"Child '{name}' not found in parent")

    child = parent._children.pop(name)
    child._parent = None
    child._name = None
    return child


def replace(parent: Node, name: str, child: Node) -> Node:
    # TN-A1: Validate name (same as attach)
    if not name or name in (".", "..") or "/" in name:
        raise InvalidTreeError(f"Invalid child name: '{name}'")

    # TN-A3: Reject self-links
    if child is parent:
        raise InvalidTreeError("Cannot replace with itself")

    # TN-A3: Reject ancestor cycles
    current = parent
    while current is not None:
        if child is current:
            raise InvalidTreeError("Cannot replace a node with one of its descendants")
        current = current.parent

    # TN-A4: Report missing children if not replacing an existing child
    if name not in parent._children and child._parent is not parent:
        raise NodeNotFoundError(f"Child '{name}' not found for replacement")

    # TN-A2: Attaching an already attached node moves its complete subtree.
    # If child is already attached elsewhere, detach it first.
    if child.parent is not None and child.parent is not parent:
        detach(child.parent, child.name)

    # Remove the old child if it exists
    old_child = None
    if name in parent._children:
        old_child = parent._children.pop(name)
        old_child._parent = None
        old_child._name = None

    # Perform the replacement
    child._parent = parent
    child._name = name
    parent._children[name] = child

    return old_child if old_child is not None else child # TN-A4: return affected node


def orphan(node: Node) -> Node:
    if node.parent is None:
        # If already orphaned, return self as per TN-A4 (return affected node)
        return node

    # TN-A4: clear detached parent/name metadata
    parent = node.parent
    name = node.name
    
    # Detach from parent
    parent._children.pop(name)
    node._parent = None
    node._name = None
    
    return node
