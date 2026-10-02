from __future__ import annotations

from .model import InvalidTreeError, Node, NodeNotFoundError, NodePath, NotInSameTreeError


def attach(parent: Node, name: str, child: Node) -> None:
    if name in (".", ".."):
        raise ValueError("Child name cannot be '.' or '..'")
    if "/" in name:
        raise ValueError("Child name cannot contain '/'")
    if not name:
        raise ValueError("Child name cannot be empty")

    if name in parent._children and parent._children[name] is not child:
        raise ValueError(f"Name '{name}' already occupied by a different node")

    # If the child is already attached elsewhere, detach it first
    if child._parent is not None and child._parent is not parent:
        # Ensure the child's name is correctly identified before detaching
        child_name = child._name
        if child_name is None:
            # This case should ideally not happen if child is attached, but for safety:
            raise InvalidTreeError("Cannot detach a node without a name")
        detach(child._parent, child_name)  # type: ignore

    # Check for self-links and ancestor cycles
    if child is parent:
        raise InvalidTreeError("Cannot attach a node to itself")
    current = parent
    while current:
        if current is child:
            raise InvalidTreeError("Cannot attach a node to its descendant")
        current = current.parent

    child._parent = parent
    child._name = name
    parent._children[name] = child


def detach(parent: Node, name: str) -> Node:
    if name not in parent._children:
        raise NodeNotFoundError(f"Node '{name}' not found under parent")

    child = parent._children[name]
    del parent._children[name]
    child._parent = None
    child._name = None
    return child


def replace(parent: Node, name: str, child: Node) -> Node:
    if name not in parent._children:
        raise NodeNotFoundError(f"Node '{name}' not found under parent")

    old_child = parent._children[name]
    
    # Detach the old child
    del parent._children[name]
    old_child._parent = None
    old_child._name = None

    # Attach the new child
    attach(parent, name, child)
    return old_child


def orphan(node: Node) -> Node:
    if node._parent is None:
        return node  # Already orphaned

    parent = node._parent
    name = node._name

    # Detach the node from its parent
    # We already know parent and name are not None because _parent is not None
    detach(parent, name)  # type: ignore
    return node
