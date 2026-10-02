from __future__ import annotations

from .model import InvalidTreeError, Node, NodeNotFoundError


def attach(parent: Node, name: str, child: Node) -> None:
    # TN-A1: Validations for name
    if not name or name in (".", "..") or "/" in name:
        raise InvalidTreeError(f"Invalid child name: '{name}'")

    # TN-A1: Reject occupied name unless replacing (replace is handled elsewhere)
    if name in parent._children and child is not parent._children[name]:
        raise InvalidTreeError(f"Name '{name}' already occupied by another node.")

    # TN-A3: Reject self-links
    if child is parent:
        raise InvalidTreeError("Cannot attach a node to itself.")

    # TN-A3: Reject ancestor cycles
    current = parent
    while current:
        if child is current:
            raise InvalidTreeError("Cannot attach a node to its descendant.")
        current = current.parent

    # If the child is already attached elsewhere, detach it first
    if child.parent is not None and child.parent is not parent:
        # Detach from its current parent, but do not raise NodeNotFoundError if it's not found (it should be found)
        # This is a move operation, so we don't need to return the detached node here.
        detach(child.parent, child.name) # type: ignore

    # TN-A2: Maintain consistent parent, name, and children views
    child._parent = parent
    child._name = name
    parent._children[name] = child


def detach(parent: Node, name: str) -> Node:
    # TN-A4: Report missing children with NodeNotFoundError
    if name not in parent._children:
        raise NodeNotFoundError(f"Child '{name}' not found in parent '{parent.name}'.")

    child = parent._children[name]

    # TN-A4: Clear detached parent/name metadata
    child._parent = None
    child._name = None
    del parent._children[name]

    # TN-A4: Return the affected node
    return child


def replace(parent: Node, name: str, child: Node) -> Node:
    # TN-A4: Report missing children with NodeNotFoundError
    if name not in parent._children:
        raise NodeNotFoundError(f"Child '{name}' not found in parent '{parent.name}'.")

    # Detach the existing child. This also clears its parent and name.
    old_child = detach(parent, name)

    # Attach the new child. This will set its parent and name.
    # The attach function will handle moving the subtree if the child is already attached elsewhere.
    attach(parent, name, child)

    # TN-A4: Return the affected node (the old child that was replaced)
    return old_child


def orphan(node: Node) -> Node:
    if node.parent is None or node.name is None:
        # Node is already orphaned or is the root (which cannot be orphaned in this manner)
        # Depending on desired behavior, could raise an error or just return the node.
        # For now, let's assume it's a no-op if already orphaned.
        return node

    # Detach the node from its parent. This will clear its parent and name.
    detached_node = detach(node.parent, node.name)

    # The detach function already returns the detached node, which is what we want.
    return detached_node
