from __future__ import annotations

from .model import Node, InvalidTreeError, NodeNotFoundError


def _check_cycle(parent: Node, child: Node) -> None:
    """Check for self-links and ancestor cycles."""
    if child is parent:
        raise InvalidTreeError("Cannot attach a node to itself.")
    
    current = parent
    while current:
        if current is child:
            raise InvalidTreeError("Cannot attach a node to one of its descendants.")
        current = current.parent


def attach(parent: Node, name: str, child: Node) -> None:
    # TN-A1: Validate name
    if not name or name in (".", "..") or "/" in name:
        raise InvalidTreeError(
            "Child name must be non-empty, not '.' or '..', and contain no '/'"
        )

    # TN-A3: Check for cycles
    _check_cycle(parent, child)

    # TN-A2: If child is already attached, detach it first
    if child.parent is not None and child.name is not None:
        # If it's being attached to its current parent with the same name, do nothing
        if child.parent is parent and child.name == name:
            return
        # Otherwise, detach it from its old parent
        try:
            # Detach the child from its current parent. This will clear the child's parent and name.
            detach(child.parent, child.name)
        except NodeNotFoundError:
            # This should not happen if child.parent and child.name are set, but for safety.
            pass

    # TN-A1: Reject occupied name unless operation is replace (handled by replace function)
    if name in parent._children:
        raise InvalidTreeError(f"Name '{name}' is already occupied in parent '{parent.name}'.")

    # Set parent and name for the child
    child._parent = parent
    child._name = name

    # Add child to parent's children dictionary
    parent._children[name] = child


def detach(parent: Node, name: str) -> Node:
    # TN-A4: Report missing children with NodeNotFoundError
    if name not in parent._children:
        raise NodeNotFoundError(f"Child '{name}' not found in parent '{parent.name}'.")

    child = parent._children[name]

    # TN-A4: Clear detached parent/name metadata
    child._parent = None
    child._name = None
    del parent._children[name]

    # TN-A2: Read-only children view is maintained by MappingProxyType in the property
    return child


def replace(parent: Node, name: str, child: Node) -> Node:
    # TN-A4: Return the affected node
    # TN-A1: rejects an occupied name unless the operation is replace
    if name not in parent._children:
        raise NodeNotFoundError(f"Child '{name}' not found for replacement in parent '{parent.name}'.")

    old_child = parent._children[name]

    # If the node to be replaced is the same as the child to attach,
    # we only need to ensure its state is correct for this parent.
    if old_child is child:
        # Ensure the parent and name are correctly set, though they should be.
        child._parent = parent
        child._name = name
        parent._children[name] = child # Ensure it's in the dictionary
        return old_child

    # Detach the old child (clear its parent and name)
    old_child._parent = None
    old_child._name = None
    del parent._children[name]

    # TN-A3: Check for cycles before attaching the new child
    _check_cycle(parent, child)

    # TN-A2: If the new child is already attached elsewhere, detach it first
    if child.parent is not None and child.name is not None:
        try:
            detach(child.parent, child.name)
        except NodeNotFoundError:
            pass # Should not happen if parent and name are set

    # Set parent and name for the new child
    child._parent = parent
    child._name = name
    parent._children[name] = child

    return old_child


def orphan(node: Node) -> Node:
    # TN-A4: return the affected node, clear detached parent/name metadata
    if node.parent:
        try:
            # Detach from parent. This will clear node._parent and node._name.
            detach(node.parent, node.name)
        except NodeNotFoundError:
            # This could happen if the tree state is inconsistent.
            # Manually clear parent and name to ensure node is orphaned.
            node._parent = None
            node._name = None
    else:
        # If node has no parent, it's already orphaned. Ensure its name is None too.
        node._name = None
        node._parent = None
    return node
