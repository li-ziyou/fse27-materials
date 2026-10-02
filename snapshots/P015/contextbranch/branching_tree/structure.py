from __future__ import annotations

from .model import Node, InvalidTreeError, NodeNotFoundError


def attach(parent: Node, name: str, child: Node) -> None:
    # TN-A1: Validates name and checks for existing child.
    if not name or name in {".", ".."} or "/" in name:
        raise InvalidTreeError(
            "Child name must be non-empty, not '.' or '..', and contain no '/'"
        )
    if name in parent._children and name != child.name:  # Check if name is occupied by a different node
        raise InvalidTreeError(f"Child name '{name}' already exists.")

    # TN-A3: Structural operations reject self-links and ancestor cycles.
    if child is parent:
        raise InvalidTreeError("Cannot attach a node to itself.")
    current = parent
    while current is not None:
        if current is child:
            raise InvalidTreeError("Cannot attach a node to one of its descendants.")
        current = current.parent

    # TN-A2: Handles moving an already attached node.
    if child.parent is not None and child.parent is not parent:
        # Detach from old parent if it exists and is not the same as the new parent
        if child.parent is not None:
            # Need to use detach from the current file, not the model's proxy
            _detach_from_parent(child.parent, child.name) # This will also clear child's parent/name

    # Set new parent and name
    child._parent = parent
    child._name = name
    parent._children[name] = child

# Helper function to avoid circular import issues with model.py's detach
def _detach_from_parent(parent: Node, name: str) -> None:
    if name not in parent._children:
        # This should ideally not happen if called from within attach/replace
        # but added for safety. It might indicate a bug elsewhere.
        return
    child_to_detach = parent._children.pop(name)
    child_to_detach._parent = None
    child_to_detach._name = None


def detach(parent: Node, name: str) -> Node:
    # TN-A4: Reports NodeNotFoundError if child is missing.
    if name not in parent._children:
        raise NodeNotFoundError(f"Child '{name}' not found.")

    child = parent._children.pop(name)
    child._parent = None
    child._name = None
    return child


def replace(parent: Node, name: str, child: Node) -> Node:
    # TN-A1: Validates name and checks for existing child.
    if not name or name in {".", ".."} or "/" in name:
        raise InvalidTreeError(
            "Child name must be non-empty, not '.' or '..', and contain no '/'"
        )
    
    # TN-A2: Handles moving an already attached node.
    if child.parent is not None and child.parent is not parent:
        if child.parent is not None:
            # Need to use detach from the current file, not the model's proxy
            _detach_from_parent(child.parent, child.name) # This will also clear child's parent/name

    # If the name already exists, detach the old child and return it.
    old_child = None
    if name in parent._children:
        old_child = detach(parent, name)

    # Attach the new child.
    child._parent = parent
    child._name = name
    parent._children[name] = child

    return old_child


def orphan(node: Node) -> Node:
    if node.parent is None:
        # Already orphaned
        return node

    parent = node.parent
    name = node.name

    # Detach from parent
    detach(parent, name)
    # detach already sets node._parent = None and node._name = None

    return node
