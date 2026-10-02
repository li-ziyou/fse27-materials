from __future__ import annotations

from .model import Node, InvalidTreeError, NodeNotFoundError


def attach(parent: Node, name: str, child: Node) -> None:
    if not name or name in (".", "..") or "/" in name:
        raise InvalidTreeError(f"Invalid child name: {name!r}")

    if name in parent._children:
        raise InvalidTreeError(f"Name {name!r} already occupied under parent {parent.path!r}")

    if child.parent is not None and child.parent is not parent:
        # Detach from old parent if it's a different node
        # This covers moving an already attached node
        if child.name is not None:
            detach(child.parent, child.name)

    # Check for self-attachment or ancestor cycle before modifying
    if child is parent:
        raise InvalidTreeError("Cannot attach a node to itself.")
    
    current = parent
    while current is not None:
        if current is child:
            raise InvalidTreeError("Cannot attach a node to one of its descendants.")
        current = current.parent

    child._parent = parent
    child._name = name
    parent._children[name] = child


def detach(parent: Node, name: str) -> Node:
    if name not in parent._children:
        raise NodeNotFoundError(f"Child {name!r} not found under parent {parent.path!r}")

    child = parent._children[name]
    child._parent = None
    child._name = None
    del parent._children[name]
    return child


def replace(parent: Node, name: str, child: Node) -> Node:
    if not name or name in (".", "..") or "/" in name:
        raise InvalidTreeError(f"Invalid child name: {name!r}")

    if name not in parent._children:
        raise NodeNotFoundError(f"Child {name!r} not found under parent {parent.path!r}")

    old_child = parent._children[name]

    # Check for self-attachment or ancestor cycle before modifying
    if child is parent:
        raise InvalidTreeError("Cannot replace with a node that is itself.")
    
    current = parent
    while current is not None:
        if current is child:
            raise InvalidTreeError("Cannot replace with a node that is a descendant.")
        current = current.parent

    # Detach the old child
    old_child._parent = None
    old_child._name = None

    # Attach the new child
    child._parent = parent
    child._name = name
    parent._children[name] = child

    return old_child


def orphan(node: Node) -> Node:
    if node.parent is None:
        # Node is already a root, nothing to do or raise error based on spec.
        # The spec implies it detaches from its parent, so if no parent, no-op.
        return node

    # Detach from its current parent
    detach(node.parent, node.name) # type: ignore

    # The detach function already sets node.parent and node.name to None
    return node
