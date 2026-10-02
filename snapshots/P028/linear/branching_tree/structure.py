from __future__ import annotations

from .model import Node, InvalidTreeError, NodeNotFoundError


def attach(parent: Node, name: str, child: Node) -> None:
    if not name or name in (".", "..") or "/" in name:
        raise InvalidTreeError("Invalid child name")

    if name in parent._children:
        raise InvalidTreeError("Name already occupied")

    if child.parent is not None:
        if child.parent is parent and child.name == name:
            # Attaching to self with same name, no-op
            return
        current_parent = child.parent
        current_name = child.name
        try:
            current_parent.detach(current_name)
        except NodeNotFoundError:
            # Should not happen if child.parent is not None
            pass

    if child is parent:
        raise InvalidTreeError("Cannot attach node to itself")

    current = parent
    while current is not None:
        if current is child:
            raise InvalidTreeError("Cannot attach node to a descendant")
        current = current.parent

    parent._children[name] = child
    child._parent = parent
    child._name = name


def detach(parent: Node, name: str) -> Node:
    if name not in parent._children:
        raise NodeNotFoundError("Child not found")

    child = parent._children.pop(name)
    child._parent = None
    child._name = None
    return child


def replace(parent: Node, name: str, child: Node) -> Node:
    if not name or name in (".", "..") or "/" in name:
        raise InvalidTreeError("Invalid child name")

    if name not in parent._children:
        raise NodeNotFoundError("Child not found for replacement")

    old_child = parent._children[name]

    if child.parent is not None:
        if child.parent is parent and child.name == name:
            # Replacing with self, no-op
            return old_child
        current_parent = child.parent
        current_name = child.name
        try:
            current_parent.detach(current_name)
        except NodeNotFoundError:
            pass

    if child is parent:
        raise InvalidTreeError("Cannot replace with self")

    current = parent
    while current is not None:
        if current is child:
            raise InvalidTreeError("Cannot replace with a descendant")
        current = current.parent

    parent._children[name] = child
    child._parent = parent
    child._name = name

    old_child._parent = None
    old_child._name = None
    return old_child


def orphan(node: Node) -> Node:
    if node.parent is None:
        return node
    parent = node.parent
    name = node.name
    try:
        parent.detach(name)
    except NodeNotFoundError:
        # Should not happen if node.parent is not None and name is set
        pass
    return node
