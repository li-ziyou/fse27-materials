from __future__ import annotations

from .model import Node, NodeNotFoundError, InvalidTreeError


def attach(parent: Node, name: str, child: Node) -> None:
    if not name or name in (".", "..") or "/" in name:
        raise InvalidTreeError(f"Invalid child name: {name}")

    if name in parent.children:
        raise InvalidTreeError(f"Child name '{name}' already exists")

    # TN-A2: If the child to be attached is already attached elsewhere, detach it first.
    if child.parent is not None and child.parent is not parent:
        # Detach from old parent, clearing its parent and name.
        if child.name is None:
             raise InvalidTreeError("Child node is already detached or in an inconsistent state")
        # Ensure we are detaching the correct child from its parent
        # This handles the case where the child might have been re-attached
        # to a different parent but still holds a reference to its old parent.
        if child.parent.children.get(child.name) is child:
            child.parent.detach(child.name)
        else:
            # If the child is not found in its parent's children, it might be detached or in an inconsistent state.
            # We should still clear its parent and name if they are set.
            child._parent = None
            child._name = None


    # TN-A3: Prevent self-links and ancestor cycles
    if child is parent:
        raise InvalidTreeError("Cannot attach a node to itself")
    
    # Check for cycles: a node cannot be attached to one of its descendants
    # We need to resolve the path to check if the child is a descendant of the parent.
    # If child.path is already defined, it means it's attached.
    # However, we are in the process of attaching, so we need to check its potential new position.
    # A simpler check is to see if the parent is a descendant of the child.
    if parent in child.descendants:
        raise InvalidTreeError("Cannot attach a node to one of its descendants (cycle detected)")

    child._parent = parent
    child._name = name
    parent._children[name] = child


def detach(parent: Node, name: str) -> Node:
    if name not in parent.children:
        raise NodeNotFoundError(f"Child '{name}' not found")
    
    child = parent.children[name]
    # Clear the parent and name of the detached child
    child._parent = None
    child._name = None
    # Remove the child from the parent's children dictionary
    del parent._children[name]
    return child


def replace(parent: Node, name: str, child: Node) -> Node:
    if name not in parent.children:
        raise NodeNotFoundError(f"Child '{name}' not found for replacement")

    # TN-A2: If the child to be attached is already attached elsewhere, detach it first.
    if child.parent is not None and child.parent is not parent:
        # Detach from old parent, clearing its parent and name.
        if child.name is None:
             raise InvalidTreeError("Child node is already detached or in an inconsistent state")
        child.detach(child.name)

    # TN-A3: Prevent self-replacement
    if child is parent:
        raise InvalidTreeError("Cannot replace a node with itself")

    # TN-A3: Prevent cycles: a node cannot replace a child with one of its descendants
    if child in parent.descendants:
        raise InvalidTreeError("Cannot replace a node with one of its descendants")

    old_child = parent.children[name]
    # Clear the old child's parent and name
    old_child._parent = None
    old_child._name = None

    # Attach the new child
    child._parent = parent
    child._name = name
    parent._children[name] = child
    return old_child


def orphan(node: Node) -> Node:
    if node.parent is None:
        # If the node is already the root, it cannot be orphaned further.
        return node

    parent = node.parent
    name = node.name
    
    # Clear the node's parent and name
    node._parent = None
    node._name = None
    # Remove the node from its parent's children dictionary
    del parent._children[name]
    return node
