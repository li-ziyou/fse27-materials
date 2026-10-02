from __future__ import annotations

from .model import Node, InvalidTreeError, NodeNotFoundError


def _check_for_cycles(parent: Node, child: Node) -> None:
    """Check for self-links and ancestor cycles."""
    if child is parent:
        raise InvalidTreeError("Cannot attach a node to itself.")

    current = parent
    while current:
        if current is child:
            raise InvalidTreeError("Cannot attach a node to its descendant (cycle detected).")
        current = current.parent


def attach(parent: Node, name: str, child: Node) -> None:
    """Attach a child node to a parent node with a given name."""
    # TN-A1: Validate name
    if not name or name in {".", ".."}:
        raise InvalidTreeError(f"Invalid child name: '{name}'. Must be non-empty and not '.' or '..'.")
    if "/" in name:
        raise InvalidTreeError(f"Invalid child name: '{name}'. Cannot contain '/'.")

    # TN-A3: Check for cycles
    _check_for_cycles(parent, child)

    # TN-A1 & TN-A2: Handle existing child
    if name in parent._children:
        raise InvalidTreeError(f"Name '{name}' is already occupied under parent '{parent.name}'. Use replace() to overwrite.")

    # TN-A2: Maintain consistent state
    if child.parent is not None and child.name is not None:
        # If child is already attached, detach it from its current parent
        current_parent = child.parent
        current_name = child.name
        try:
            # Temporarily remove from current parent to avoid issues if current_parent is parent
            del current_parent._children[current_name]
            child._parent = None
            child._name = None
        except KeyError:
            # This should ideally not happen if state is consistent, but good for robustness
            pass

    parent._children[name] = child
    child._parent = parent
    child._name = name


def detach(parent: Node, name: str) -> Node:
    """Detach a child node from a parent node by name."""
    # TN-A4: Report missing children
    if name not in parent._children:
        raise NodeNotFoundError(f"Child '{name}' not found under parent '{parent.name}'.")

    child = parent._children[name]
    del parent._children[name]

    # TN-A4: Clear detached parent/name metadata
    child._parent = None
    child._name = None

    return child


def replace(parent: Node, name: str, child: Node) -> Node:
    """Replace a child node with a new one."""
    # TN-A1: Validate name (same as attach)
    if not name or name in {".", ".."}:
        raise InvalidTreeError(f"Invalid child name: '{name}'. Must be non-empty and not '.' or '..'.")
    if "/" in name:
        raise InvalidTreeError(f"Invalid child name: '{name}'. Cannot contain '/'.")

    # TN-A3: Check for cycles
    _check_for_cycles(parent, child)

    # TN-A4: Report missing children if name doesn't exist
    if name not in parent._children:
        raise NodeNotFoundError(f"Child '{name}' not found under parent '{parent.name}'. Cannot replace non-existent child.")

    old_child = parent._children[name]

    # TN-A2: Maintain consistent state
    if child.parent is not None and child.name is not None:
        # If child is already attached, detach it from its current parent
        current_parent = child.parent
        current_name = child.name
        try:
            del current_parent._children[current_name]
            child._parent = None
            child._name = None
        except KeyError:
            pass

    parent._children[name] = child
    child._parent = parent
    child._name = name

    # TN-A4: Clear detached parent/name metadata of the old child
    old_child._parent = None
    old_child._name = None

    return old_child


def orphan(node: Node) -> Node:
    """Orphan a node, detaching it from its parent."""
    # TN-A4: Handle attempting to orphan the root
    if node.parent is None:
        raise InvalidTreeError("Cannot orphan the root node.")

    parent = node.parent
    name = node.name

    # Detach the node from its parent
    # This also clears node._parent and node._name
    detached_node = detach(parent, name)

    return detached_node
