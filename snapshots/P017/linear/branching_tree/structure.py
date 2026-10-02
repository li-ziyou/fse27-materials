from __future__ import annotations

from .model import Node, InvalidTreeError, NodeNotFoundError, NotInSameTreeError


def attach(parent: Node, name: str, child: Node) -> None:
    # TN-A1: accepts a non-empty child name other than `.` or `..` with no `/`
    if not name or name in (".", "..") or "/" in name:
        raise ValueError("Invalid child name")

    # TN-A1: rejects an occupied name unless the operation is `replace` (handled by replace function)
    if name in parent._children:
        raise ValueError(f"Name '{name}' already occupied")

    # TN-A3: reject self-links
    if child is parent:
        raise InvalidTreeError("Cannot attach a node to itself")

    # TN-A3: reject ancestor cycles
    current = parent
    while current is not None:
        if child is current:
            raise InvalidTreeError("Cannot attach a node below one of its ancestors")
        current = current.parent

    # TN-A2: attaching an already attached node moves its complete subtree.
    if child.parent is not None and child.parent is not parent:
        # This is a move operation. The detach function handles clearing parent/name.
        detach(child.parent, child.name) # type: ignore

    # Set new parent and name
    child._parent = parent
    child._name = name
    parent._children[name] = child


def detach(parent: Node, name: str) -> Node:
    # TN-A4: report missing children with NodeNotFoundError
    if name not in parent._children:
        raise NodeNotFoundError(f"Child '{name}' not found in parent")

    child = parent._children[name]
    del parent._children[name]
    child._parent = None
    child._name = None
    return child


def replace(parent: Node, name: str, child: Node) -> Node:
    # TN-A1: accepts a non-empty child name other than `.` or `..` with no `/`
    if not name or name in (".", "..") or "/" in name:
        raise ValueError("Invalid child name")

    # Check if the name exists, if not, it's an error for replace.
    if name not in parent._children:
        raise NodeNotFoundError(f"Child '{name}' not found for replacement")

    # TN-A3: reject self-links
    if child is parent:
        raise InvalidTreeError("Cannot replace with a node that is itself")

    # TN-A3: reject ancestor cycles
    current = parent
    while current is not None:
        if child is current:
            raise InvalidTreeError("Cannot replace with a node that is an ancestor")
        current = current.parent

    old_child = parent._children[name]

    # If the child is already attached elsewhere, detach it.
    # TN-A2: attaching an already attached node moves its complete subtree.
    if child.parent is not None and child.parent is not parent:
        # This is a move operation. The detach function handles clearing parent/name.
        detach(child.parent, child.name) # type: ignore

    # Set new parent and name for the new child
    child._parent = parent
    child._name = name
    parent._children[name] = child

    # Clear parent and name for the old child
    old_child._parent = None
    old_child._name = None

    return old_child


def orphan(node: Node) -> Node:
    if node.parent is None:
        raise InvalidTreeError("Cannot orphan the root node")

    parent = node.parent
    name = node.name

    # Detach the node from its parent
    detached_node = detach(parent, name) # type: ignore

    return detached_node
