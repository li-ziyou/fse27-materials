from __future__ import annotations

from .model import Node, InvalidTreeError, NodeNotFoundError


def attach(parent: Node, name: str, child: Node) -> None:
    # TN-A1: Validate name
    if not name or name in (".", "..") or "/" in name:
        raise InvalidTreeError(
            f"Child name '{name}' must be non-empty, not '.' or '..', and contain no '/'."
        )

    # TN-A3: Reject self-links and ancestor cycles
    if child is parent:
        raise InvalidTreeError("Cannot attach a node to itself.")
    current = parent
    while current:
        if child is current:
            raise InvalidTreeError("Cannot attach a node to one of its descendants.")
        current = current.parent

    # TN-A1: Reject occupied name unless it's the same child (no-op)
    existing_child = parent._children.get(name)
    if existing_child is not None:
        if existing_child is child:
            # Already attached, no-op
            return
        else:
            raise InvalidTreeError(f"Name '{name}' is already occupied by another node.")

    # TN-A2: If child is already attached elsewhere, detach it first
    if child.parent is not None:
        # Ensure we don't detach the child from itself if it's being moved
        # to its own parent with a different name. This is covered by TN-A3 check.
        if child.parent is not parent or child.name != name:
            # Detach from its current parent
            current_parent = child.parent
            current_name = child.name
            # Use internal method to avoid checks/exceptions during move
            current_parent._children.pop(current_name)
            child._parent = None
            child._name = None

    # Perform the attachment
    child._parent = parent
    child._name = name
    parent._children[name] = child


def detach(parent: Node, name: str) -> Node:
    # TN-A4: Report missing children
    if name not in parent._children:
        raise NodeNotFoundError(f"No child named '{name}' found to detach.")

    child = parent._children[name]
    # Clear detached parent/name metadata
    child._parent = None
    child._name = None
    parent._children.pop(name)
    return child


def replace(parent: Node, name: str, child: Node) -> Node:
    # TN-A4: Report missing children
    if name not in parent._children:
        raise NodeNotFoundError(f"No child named '{name}' found to replace.")

    # Detach the existing child (this also clears its parent/name)
    old_child = parent.detach(name)

    # Attach the new child
    # We use the internal attach logic here to avoid re-checking name validity,
    # as we've already confirmed the slot is free after detach.
    # TN-A2: attaching an already attached node moves its complete subtree.
    # This is handled by the detach logic above.
    child._parent = parent
    child._name = name
    parent._children[name] = child

    return old_child


def orphan(node: Node) -> Node:
    # TN-A4: clear detached parent/name metadata
    if node.parent is None:
        return node  # Already orphaned

    parent = node.parent
    name = node.name
    # Use internal detach to avoid exceptions if node.parent is None,
    # which is handled by the check above.
    parent._children.pop(name)
    node._parent = None
    node._name = None
    return node
