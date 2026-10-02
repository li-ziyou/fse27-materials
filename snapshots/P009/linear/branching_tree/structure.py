from __future__ import annotations

from .model import Node, InvalidTreeError, NodeNotFoundError


def attach(parent: Node, name: str, child: Node) -> None:
    """
    Attach a child node to a parent node with a given name.

    TN-A1: Validates the name and checks for existing children.
    TN-A2: Ensures parent, name, and children are consistent. Handles moving existing nodes.
    TN-A3: Prevents self-attachment and cycles.
    """
    # TN-A1: Validate name
    if not name or name in {".", ".."}:
        raise InvalidTreeError(f"Invalid child name: '{name}'")
    if "/" in name:
        raise InvalidTreeError(f"Child name cannot contain '/': '{name}'")

    # TN-A3: Prevent self-attachment and cycles
    if child is parent:
        raise InvalidTreeError("Cannot attach a node to itself.")
    current = parent
    while current is not None:
        if current is child:
            raise InvalidTreeError("Cannot attach a node to one of its descendants.")
        current = current.parent

    # TN-A1: Reject occupied name unless operation is replace (handled by caller)
    if name in parent._children:
        raise InvalidTreeError(f"Name '{name}' is already occupied by another child.")

    # If the child is already attached, detach it first
    # This must happen *after* checking for cycles and name conflicts,
    # to ensure no tree modifications occur if the operation is invalid.
    if child.parent is not None and child.name is not None:
        # TN-A2: Attaching an already attached node moves its complete subtree.
        child.parent.detach(child.name) # type: ignore

    # Attach the child
    child._parent = parent
    child._name = name
    parent._children[name] = child


def detach(parent: Node, name: str) -> Node:
    """
    Detach a child node from its parent.

    TN-A4: Returns the affected node, clears detached parent/name metadata,
           and reports missing children with NodeNotFoundError.
    """
    if name not in parent._children:
        raise NodeNotFoundError(f"Child '{name}' not found in parent.")

    child = parent._children[name]

    # Clear parent and name metadata from the detached child
    child._parent = None
    child._name = None

    # Remove from parent's children dictionary
    del parent._children[name]

    return child


def replace(parent: Node, name: str, child: Node) -> Node:
    """
    Replace an existing child node with a new child node.

    TN-A2: Maintains consistent parent, name, and children views.
    TN-A4: Returns the affected node, clears detached parent/name metadata.
    """
    if name not in parent._children:
        raise NodeNotFoundError(f"Child '{name}' not found in parent.")

    # Detach the old child
    old_child = parent.detach(name)

    # Attach the new child
    # The attach function handles moving the subtree if the child is already attached
    parent.attach(name, child)

    return old_child


def orphan(node: Node) -> Node:
    """
    Orphan a node, detaching it from its parent.

    TN-A4: Returns the affected node, clears detached parent/name metadata.
    """
    if node.parent is None or node.name is None:
        # Node is already orphaned or is the root
        return node

    # Detach the node from its parent
    detached_node = node.parent.detach(node.name)

    return detached_node
