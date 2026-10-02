from __future__ import annotations

from .model import Node, InvalidTreeError, NodeNotFoundError


def attach(parent: Node, name: str, child: Node) -> None:
    # TN-A1: accept non-empty child name other than '.' or '..' with no '/'
    if not name or name in {".", ".."} or "/" in name:
        raise ValueError(
            "Child name must be non-empty and cannot contain '.' or '/'"
        )

    # TN-A1: reject occupied name unless the operation is 'replace'
    if name in parent._children and name != child.name:
        raise ValueError(f"Name '{name}' is already occupied")

    # TN-A3: reject self-links
    if child is parent:
        raise InvalidTreeError("Cannot attach a node to itself")

    # TN-A3: reject ancestor cycles
    current = parent
    while current:
        if child is current:
            raise InvalidTreeError("Cannot attach a node to an ancestor")
        current = current.parent

    # If the child is already attached elsewhere, detach it first
    if child.parent is not None and child.parent is not parent:
        # TN-A2: attaching an already attached node moves its complete subtree.
        # Detach from old parent without raising NodeNotFoundError if child.name is not in old parent's children
        # (this can happen if child was moved from elsewhere and its old parent's children dict is stale)
        if child.name in child.parent._children and child.parent._children[child.name] is child:
            detach(child.parent, child.name)
        # Even if not found in old parent's children, clear the old parent/name refs
        child._parent = None
        child._name = None

    # TN-A2: maintain consistent parent, name, and read-only children views
    child._parent = parent
    child._name = name
    parent._children[name] = child


def detach(parent: Node, name: str) -> Node:
    # TN-A4: report missing children with NodeNotFoundError
    if name not in parent._children:
        raise NodeNotFoundError(f"Child '{name}' not found in parent '{parent.name}'")

    child = parent._children.pop(name)
    child._parent = None
    child._name = None
    return child


def replace(parent: Node, name: str, child: Node) -> Node:
    # TN-A1: reject occupied name unless the operation is 'replace'
    if name not in parent._children:
        raise NodeNotFoundError(f"Child '{name}' not found for replacement")

    # TN-A3: reject self-links
    if child is parent:
        raise InvalidTreeError("Cannot replace a node with itself")

    # TN-A3: reject ancestor cycles
    current = parent
    while current:
        if child is current:
            raise InvalidTreeError("Cannot replace a node with an ancestor")
        current = current.parent

    # If the child is already attached elsewhere, detach it first
    if child.parent is not None and child.parent is not parent:
        # TN-A2: attaching an already attached node moves its complete subtree.
        if child.name in child.parent._children and child.parent._children[child.name] is child:
            detach(child.parent, child.name)
        child._parent = None
        child._name = None

    old_child = parent._children.pop(name) # Remove the old child from parent's children
    old_child._parent = None # Clear parent and name from the old child
    old_child._name = None
    child._parent = parent
    child._name = name
    parent._children[name] = child
    return old_child


def orphan(node: Node) -> Node:
    if node.parent is None:
        # Cannot orphan a root node that has no parent
        raise InvalidTreeError("Cannot orphan a root node")

    # TN-A4: clear detached parent/name metadata
    parent = node.parent
    name = node.name
    if name is None:
        # This should not happen if the node is attached to a parent
        raise InvalidTreeError("Node to be orphaned has no name")

    # Detach from parent
    if name in parent._children and parent._children[name] is node:
        parent._children.pop(name)
    node._parent = None
    node._name = None
    return node
