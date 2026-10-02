from __future__ import annotations

from .model import Node, InvalidTreeError, NodeNotFoundError
from .navigation import absolute_path, NodePath


def attach(parent: Node, name: str, child: Node) -> None:
    if not name or name in (".", "..") or "/" in name:
        raise InvalidTreeError(f"Invalid child name: {name!r}")

    if name in parent._children:
        raise InvalidTreeError(f"Name collision: {name!r} already exists under {parent.path}")

    if child._parent is not None or child._name is not None:
        # If child is already attached, detach it first.
        # This handles moving subtrees.
        if child._parent is not None:
            try:
                child.detach(child.name)
            except NodeNotFoundError:
                # This should not happen if child._name is set, but handle defensively.
                pass

    child._parent = parent
    child._name = name
    parent._children[name] = child


def detach(parent: Node, name: str) -> Node:
    if name not in parent._children:
        raise NodeNotFoundError(f"Child {name!r} not found under {parent.path}")

    child = parent._children.pop(name)
    child._parent = None
    child._name = None
    return child


def replace(parent: Node, name: str, child: Node) -> Node:
    if name not in parent._children:
        raise NodeNotFoundError(f"Child {name!r} not found under {parent.path}")

    old_child = parent._children.pop(name)
    old_child._parent = None
    old_child._name = None

    if child._parent is not None or child._name is not None:
        # If child is already attached, detach it first.
        if child._parent is not None:
            try:
                child.detach(child.name)
            except NodeNotFoundError:
                pass

    child._parent = parent
    child._name = name
    parent._children[name] = child
    return old_child


def orphan(node: Node) -> Node:
    if node._parent is None:
        raise InvalidTreeError("Node is already orphaned.")

    parent = node._parent
    name = node._name

    try:
        parent.detach(name)
    except NodeNotFoundError:
        # This should not happen if node._parent and node._name are set correctly,
        # but handle defensively.
        pass

    return node
