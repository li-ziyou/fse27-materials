from __future__ import annotations

from .model import InvalidTreeError, Node, NodeNotFoundError


def attach(parent: Node, name: str, child: Node) -> None:
    # TN-A1: Validate child name
    if not name or name in (".", "..") or "/" in name:
        raise InvalidTreeError(
            "Child name must be non-empty, not '.' or '..', and contain no '/'"
        )

    # TN-A1: Reject occupied name unless it's a replace operation (handled by replace function)
    if name in parent._children and name != child.name:
        raise InvalidTreeError(f"Name '{name}' is already occupied.")

    # TN-A2: Handle attaching an already attached node (move subtree)
    if child.parent is not None and child.parent is not parent:
        # Detach from old parent before attaching to new parent
        if child.parent:
            detach(child.parent, child.name)  # type: ignore[arg-type]

    # TN-A3 & Ours: Reject self-links and ancestor cycles
    if child is parent:
        raise InvalidTreeError("Cannot attach a node to itself.")

    # Check for ancestor cycles: parent cannot be a descendant of child
    current = child
    while current.parent:
        if current.parent is parent:
            raise InvalidTreeError("Cannot attach a node to one of its descendants.")
        current = current.parent

    # Check for ancestor cycles: child cannot be a descendant of parent
    current = parent
    while current is not None:
        if current is child:
            raise InvalidTreeError("Cannot attach a node in a way that creates an ancestor cycle.")
        current = current.parent

    # Perform the attachment
    child._parent = parent
    child._name = name
    parent._children[name] = child


def detach(parent: Node, name: str) -> Node:
    """Remove and return a child node from the parent."""
    if name not in parent._children:
        raise NodeNotFoundError(f"Child '{name}' not found in parent.")

    child = parent._children.pop(name)
    child._parent = None
    child._name = None
    return child


def replace(parent: Node, name: str, child: Node) -> Node:
    """Replace an existing child node with a new one."""
    if child is parent:
        raise InvalidTreeError("Cannot replace a node with itself.")
    if name in {".", ".."}:
        raise InvalidTreeError("Child name cannot be '.' or '..'.")
    if name not in parent._children:
        raise NodeNotFoundError(f"Child '{name}' not found for replacement.")

    # Check for ancestor cycles before detaching the old child
    current = parent
    while current is not None:
        if current is child:
            raise InvalidTreeError("Cannot replace a node in a way that creates an ancestor cycle.")
        current = current.parent

    old_child = parent._children[name]
    # Detach the old child before attaching the new one to avoid issues if they are related
    # Detach will clear parent and name from old_child
    detach(parent, name)

    # Attach the new child. This will set its parent and name.
    attach(parent, name, child)

    return old_child


def orphan(node: Node) -> Node:
    """Remove a node from its parent and return it."""
    if node.parent is None:
        # Already orphaned or is the root
        return node
    
    parent = node.parent
    name = node.name
    
    if name is None:
        raise InvalidTreeError("Cannot orphan a node without a name.") # Should not happen in a valid tree

    # Safeguard against inconsistent tree state
    if name not in parent._children or parent._children[name] is not node:
        raise InvalidTreeError("Node is not correctly attached to its parent.")

    detached_node = detach(parent, name)
    return detached_node
