from __future__ import annotations

from .model import Node, InvalidTreeError, NodeNotFoundError


def attach(parent: Node, name: str, child: Node) -> None:
    if name in {".", ".."}:
        raise InvalidTreeError(f"Invalid child name: '{name}'")
    if "/" in name:
        raise InvalidTreeError(f"Invalid child name: '{name}'")
    if not name:
        raise InvalidTreeError("Child name cannot be empty.")

    if name in parent._children:
        # TN-A1: reject an occupied name unless the operation is replace.
        # This function is attach, so we reject.
        raise NodeNotFoundError(f"Child '{name}' already exists.")

    # TN-A3: structural operations reject self-links and ancestor cycles
    if child is parent:
        raise InvalidTreeError("Cannot attach a node to itself.")
    current = parent
    while current is not None:
        if current is child:
            raise InvalidTreeError("Cannot attach a node to its descendant.")
        current = current.parent
    
    # Detach child from its current parent if it has one
    if child.parent is not None:
        # This is a move operation, so we need to detach from the old parent.
        # We need to ensure the child is not already attached to the target parent
        # with the same name. If it is, it's a no-op or an error depending on
        # whether it's a move or replace. For attach, it's an error if the name exists.
        if child.parent is parent and child.name == name:
            # Already attached with the same name, this should ideally not happen
            # if the name check above is done correctly, but as a safeguard.
            # Or if it's a move to the same parent and same name, it's a no-op.
            # However, the spec says "attaching an already attached node moves its complete subtree."
            # So we should detach and re-attach to ensure consistency.
            pass # Proceed to detach and re-attach
        else:
            # Detach from old parent
            try:
                child.parent.detach(child.name)
            except NodeNotFoundError:
                # This should not happen if the tree is consistent, but handle defensively.
                pass # Already detached or inconsistent state

    # TN-A2: maintain consistent parent, name, and children views
    child._parent = parent
    child._name = name
    parent._children[name] = child


def detach(parent: Node, name: str) -> Node:
    if name not in parent._children:
        raise NodeNotFoundError(f"Child '{name}' not found.")

    child_to_detach = parent._children[name]
    del parent._children[name]

    # TN-A4: clear detached parent/name metadata
    child_to_detach._parent = None
    child_to_detach._name = None

    return child_to_detach


def replace(parent: Node, name: str, child: Node) -> Node:
    raise NotImplementedError


def orphan(node: Node) -> Node:
    raise NotImplementedError
