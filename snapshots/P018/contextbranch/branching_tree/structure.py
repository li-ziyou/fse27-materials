from __future__ import annotations

from .model import Node, InvalidTreeError, NodeNotFoundError


def attach(parent: Node, name: str, child: Node) -> None:
    # TN-A1: attach accepts a non-empty child name other than . or .. with no /,
    # and rejects an occupied name unless the operation is replace.
    if not name or name in (".", "..") or "/" in name:
        raise InvalidTreeError(f"Invalid child name: '{name}'")

    if name in parent._children and name != child.name:
        raise InvalidTreeError(f"Child name '{name}' already exists under parent.")

    # TN-A3: structural operations reject self-links and ancestor cycles
    if child is parent:
        raise InvalidTreeError("Cannot attach a node to itself.")

    current_parent = child.parent
    if current_parent is not None:
        # If the child is already attached, we need to detach it first.
        # This handles moving a node and its subtree.
        if child.name in current_parent._children:
            # Detach the child from its current parent before checking for cycles.
            # This ensures that if the child is being moved, its old parent link is severed.
            detach(current_parent, child.name)
    
    # TN-A3: structural operations reject self-links and ancestor cycles
    # Check if the parent is a descendant of the child. This would create a cycle.
    if parent in child.descendants:
        raise InvalidTreeError("Cannot attach a node to one of its descendants.")

    child._parent = parent
    child._name = name
    parent._children[name] = child


def detach(parent: Node, name: str) -> Node:
    # TN-A4: detach, replace, and orphan return the affected node, clear detached parent/name metadata, and report missing children with NodeNotFoundError.
    if name not in parent._children:
        raise NodeNotFoundError(f"Child '{name}' not found under parent.")

    child = parent._children.pop(name)
    child._parent = None
    child._name = None
    return child


def replace(parent: Node, name: str, child: Node) -> Node:
    # TN-A1: attach accepts a non-empty child name other than . or .. with no /,
    # and rejects an occupied name unless the operation is replace.
    if not name or name in (".", "..") or "/" in name:
        raise InvalidTreeError(f"Invalid child name: '{name}'")

    # TN-A2: attach and replace maintain consistent parent, name, and read-only children views;
    # attaching an already attached node moves its complete subtree.
    # If the child is already attached and has a different name, detach it first.
    if child.name is not None and child.name != name and child.parent is not None:
        if child.name in child.parent._children:
            detach(child.parent, child.name)

    # TN-A3: structural operations reject self-links and ancestor cycles
    if child is parent:
        raise InvalidTreeError("Cannot replace a node with itself.")

    if name in parent._children:
        old_child = parent._children[name]
        # TN-A4: detach, replace, and orphan return the affected node, clear detached parent/name metadata, and report missing children with NodeNotFoundError.
        if old_child is not child:
            # Detach the old child before attaching the new one
            detach(parent, name)
    else:
        old_child = None

    # TN-A3: check for ancestor cycles
    # This check needs to be done *before* detaching the old child or attaching the new one
    # to correctly identify cycles where the parent is a descendant of the child.
    if parent in child.ancestors:
        raise InvalidTreeError("Cannot replace a node with one of its descendants.")

    child._parent = parent
    child._name = name
    parent._children[name] = child

    return old_child if old_child is not None else child # TN-A4: return the affected node


def orphan(node: Node) -> Node:
    # TN-A4: detach, replace, and orphan return the affected node, clear detached parent/name metadata, and report missing children with NodeNotFoundError.
    if node.parent is None or node.name is None:
        # This case should ideally not happen if the node is properly attached,
        # but as a safeguard, we can raise an error or return the node itself.
        # Raising an error might be more indicative of an unexpected state.
        raise InvalidTreeError("Node is already orphaned or not properly attached.")

    parent = node.parent
    name = node.name
    
    # Detach the node from its parent
    detached_node = parent.detach(name)
    
    # The detach method already clears parent and name metadata.
    return detached_node
