from __future__ import annotations

from .model import Node, InvalidTreeError, NodeNotFoundError


def attach(parent: Node, name: str, child: Node) -> None:
    # TN-A1: Validate child name
    if not name or name in (".", "..") or "/" in name:
        raise InvalidTreeError(f"Invalid child name: '{name}'")

    # TN-A1: Reject occupied name unless it's a replace operation (handled by replace function)
    if name in parent._children:
        raise InvalidTreeError(f"Name '{name}' already exists under parent.")

    # TN-A2: If child is already attached, detach it first to move its subtree
    if child.parent is not None:
        # This will raise NodeNotFoundError if child.name is not found in child.parent._children,
        # which shouldn't happen if child.parent is correctly set.
        child.parent.detach(child.name)

    # TN-A3: Reject self-links and ancestor cycles
    if child is parent:
        raise InvalidTreeError("Cannot attach a node to itself.")
    current = parent
    while current is not None:
        if current is child:
            raise InvalidTreeError("Cannot attach a node to one of its descendants.")
        current = current.parent

    # Attach the child
    child._parent = parent
    child._name = name
    parent._children[name] = child


def detach(parent: Node, name: str) -> Node:
    # TN-A4: Report missing children with NodeNotFoundError
    if name not in parent._children:
        raise NodeNotFoundError(f"No child named '{name}' found under parent.")

    child = parent._children[name]

    # TN-A4: Clear detached parent/name metadata
    child._parent = None
    child._name = None
    del parent._children[name]

    # TN-A4: Return the affected node
    return child


def replace(parent: Node, name: str, child: Node) -> Node:
    # TN-A1: Reject occupied name unless the operation is replace.
    if name not in parent._children:
        raise NodeNotFoundError(f"Name '{name}' does not exist for replacement.")

    # TN-A2: Attaching an already attached node moves its complete subtree.
    # If the child to be replaced is the same as the new child, do nothing.
    if parent._children[name] is child:
        return child

    # Detach the existing child
    old_child = parent.detach(name)

    # Attach the new child
    # Note: attach function handles TN-A1 (name validation), TN-A2 (moving subtree if child is already attached),
    # and TN-A3 (self-links and ancestor cycles).
    try:
        parent.attach(name, child)
    except InvalidTreeError as e:
        # If attaching the new child fails, re-attach the old child to maintain atomicity
        parent.attach(name, old_child)
        raise e

    # TN-A4: Return the replaced node
    return old_child


def orphan(node: Node) -> Node:
    if node.parent is None or node.name is None:
        # Node is already orphaned or not properly attached
        return node

    # TN-A4: Clear detached parent/name metadata
    parent = node.parent
    name = node.name
    node._parent = None
    node._name = None

    # Remove from parent's children
    del parent._children[name]

    # TN-A4: Return the affected node
    return node
