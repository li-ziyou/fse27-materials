from __future__ import annotations

from .model import InvalidTreeError, Node, NodeNotFoundError


def _validate_name(name: str) -> None:
    """Validate that a name is acceptable for a child node."""
    if not name or name == "." or name == ".." or "/" in name:
        raise InvalidTreeError(f"Invalid name: {name!r}")


def _is_ancestor(potential_ancestor: Node, node: Node) -> bool:
    """Check if potential_ancestor is an ancestor of node."""
    current = node
    while current is not None:
        if current is potential_ancestor:
            return True
        current = current.parent
    return False


def attach(parent: Node, name: str, child: Node) -> None:
    """Attach a child to a parent with the given name.
    
    TN-A1: Validate name and reject occupied names unless replacing.
    TN-A2: Move complete subtree if child is already attached.
    TN-A3: Reject self-links and ancestor cycles atomically.
    """
    # Validate name (TN-A1)
    _validate_name(name)
    
    # Check for self-link (TN-A3)
    if parent is child:
        raise InvalidTreeError("Cannot attach a node to itself")
    
    # Check for ancestor cycle (TN-A3)
    if _is_ancestor(child, parent):
        raise InvalidTreeError("Cannot attach an ancestor as a child")
    
    # Check if name is occupied (TN-A1)
    if name in parent._children and parent._children[name] is not child:
        raise InvalidTreeError(f"Name {name!r} is already occupied")
    
    # If child is already attached elsewhere, detach it first (TN-A2)
    if child._parent is not None:
        old_parent = child._parent
        old_name = child._name
        if old_name in old_parent._children:
            del old_parent._children[old_name]
    
    # Attach the child
    parent._children[name] = child
    child._parent = parent
    child._name = name


def detach(parent: Node, name: str) -> Node:
    """Detach and return a child by name.
    
    TN-A4: Return the affected node, clear metadata, report missing with NodeNotFoundError.
    """
    if name not in parent._children:
        raise NodeNotFoundError(name)
    
    child = parent._children[name]
    del parent._children[name]
    child._parent = None
    child._name = None
    return child


def replace(parent: Node, name: str, child: Node) -> Node:
    """Replace a child and return the old child.
    
    TN-A1: Accept occupied name for replace operation.
    TN-A2: Maintain consistency; moving a subtree.
    TN-A3: Reject self-links and ancestor cycles.
    TN-A4: Return the affected node, clear old child metadata.
    """
    # Validate name (TN-A1)
    _validate_name(name)
    
    # Check for self-link (TN-A3)
    if parent is child:
        raise InvalidTreeError("Cannot attach a node to itself")
    
    # Check for ancestor cycle (TN-A3)
    if _is_ancestor(child, parent):
        raise InvalidTreeError("Cannot attach an ancestor as a child")
    
    # Get the old child if it exists
    old_child = parent._children.get(name)
    
    # If child is already attached elsewhere, detach it first (TN-A2)
    if child._parent is not None:
        old_parent = child._parent
        old_name = child._name
        if old_name in old_parent._children:
            del old_parent._children[old_name]
    
    # Replace the child
    parent._children[name] = child
    child._parent = parent
    child._name = name
    
    # Clear the old child's metadata if it existed (TN-A4)
    if old_child is not None:
        old_child._parent = None
        old_child._name = None
    
    return old_child


def orphan(node: Node) -> Node:
    """Detach and return this node from its parent.
    
    TN-A4: Return the node, clear parent/name metadata.
    """
    if node._parent is not None:
        parent = node._parent
        name = node._name
        if name in parent._children:
            del parent._children[name]
    
    node._parent = None
    node._name = None
    return node
