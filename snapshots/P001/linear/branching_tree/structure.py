from __future__ import annotations

from .model import Node, InvalidTreeError, NodeNotFoundError


def attach(parent: Node, name: str, child: Node) -> None:
    # TN-A1: name validation
    if not name or name in (".", "..") or "/" in name:
        raise InvalidTreeError(f"Invalid child name: '{name}'")

    # TN-A3: reject self-links
    if child is parent:
        raise InvalidTreeError("Cannot attach a node to itself")

    # TN-A3: reject ancestor cycles
    current = parent
    while current:
        if child is current:
            raise InvalidTreeError("Cannot attach a node to an ancestor")
        current = current.parent

    # TN-A1, TN-A2: handle occupied name
    if name in parent._children:
        if parent._children[name] is not child:
            raise InvalidTreeError(f"Name '{name}' is already occupied")
        return

    # Detach child from its current parent if it has one (TN-A2)
    if child.parent is not None:
        if child.parent is not parent: # Only detach if it's not already a child of this parent
            detach(child.parent, child.name) # This will clear child's parent and name

    # Attach child to the new parent
    child._parent = parent
    child._name = name
    parent._children[name] = child


def detach(parent: Node, name: str) -> Node:
    # TN-A4: report missing children
    if name not in parent._children:
        raise NodeNotFoundError(f"No child named '{name}' found under '{parent.name}'")

    child = parent._children.pop(name)
    child._parent = None
    child._name = None
    return child


def replace(parent: Node, name: str, child: Node) -> Node:
    # TN-A4: return the affected node
    if name not in parent._children:
        raise NodeNotFoundError(f"No child named '{name}' found under '{parent.name}'")

    old_child = parent._children[name]
    # TN-A2: attaching an already attached node moves its complete subtree
    if old_child is not child:
        detach(parent, name)
        attach(parent, name, child)
    else:
        attach(parent, name, child) # This will ensure parent/name are correct.

    return old_child


def orphan(node: Node) -> Node:
    # TN-A4: return the affected node, clear detached parent/name metadata
    if node.parent is None:
        # If node has no parent, it's already orphaned.
        return node
    parent = node.parent
    name = node.name
    # Detach the node from its parent. detach() will clear node's parent and name.
    detached_node = detach(parent, name)
    return detached_node
