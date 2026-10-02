from __future__ import annotations

from .model import InvalidTreeError, Node


def attach(parent: Node, name: str, child: Node) -> None:
    """TN-A1, TN-A2, TN-A3: Add or move a child under this node."""
    # TN-A1: Validate name
    if not name or name in (".", "..") or "/" in name:
        raise InvalidTreeError(f"Invalid child name: {name}")
    
    if name in parent._children:
        raise InvalidTreeError(f"Child name {name!r} already exists.")

    # TN-A3: Check for cycles (child cannot be parent or ancestor of parent)
    if _is_ancestor_or_self(parent, child):
        raise InvalidTreeError("Cannot attach a node to its own descendant")
    
    # If child already has a parent, detach it first (move operation)
    if child._parent is not None:
        # Atomically check before detaching
        old_parent = child._parent
        old_name = child._name
        if old_name in old_parent._children:
            old_parent._children.pop(old_name)
    
    # TN-A2: Attach the child
    child._parent = parent
    child._name = name
    parent._children[name] = child


def detach(parent: Node, name: str) -> Node:
    """TN-A4: Remove and return a child."""
    if name not in parent._children:
        from .model import NodeNotFoundError
        raise NodeNotFoundError(f"Child '{name}' not found")
    
    child = parent._children.pop(name)
    child._parent = None
    child._name = None
    return child


def replace(parent: Node, name: str, child: Node) -> Node:
    """TN-A1, TN-A2, TN-A3, TN-A4: Replace and return a child."""
    # TN-A1: Validate name
    if not name or name in (".", "..") or "/" in name:
        raise InvalidTreeError(f"Invalid child name: {name}")
    
    # TN-A3: Check for cycles
    if _is_ancestor_or_self(parent, child):
        raise InvalidTreeError("Cannot replace with a node in the same branch")
    
    if name not in parent._children:
        from .model import NodeNotFoundError
        raise NodeNotFoundError(f"Child '{name}' not found")
    
    old_child = parent._children[name]
    
    # If child already has a parent, detach it first
    if child._parent is not None:
        old_parent = child._parent
        old_name = child._name
        if old_name in old_parent._children:
            old_parent._children.pop(old_name)
    
    # Replace the child
    child._parent = parent
    child._name = name
    parent._children[name] = child
    
    # Clear old child's metadata
    old_child._parent = None
    old_child._name = None
    
    return old_child


def orphan(node: Node) -> Node:
    """TN-A4: Detach and return this node."""
    if node._parent is None:
        raise InvalidTreeError("Cannot orphan a node with no parent")
    
    parent = node._parent
    name = node._name
    return detach(parent, name)


def _is_ancestor_or_self(potential_child: Node, potential_ancestor: Node) -> bool:
    """Check if potential_ancestor is the potential_child or an ancestor of it."""
    current = potential_child
    while current is not None:
        if current is potential_ancestor:
            return True
        current = current._parent
    return False
