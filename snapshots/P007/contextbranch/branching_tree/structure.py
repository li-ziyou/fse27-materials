from __future__ import annotations

from .model import Node, InvalidTreeError, NodeNotFoundError


def attach(parent: Node, name: str, child: Node) -> None:
    # TN-A1: Validate child name
    if not name or name in (".", "..") or "/" in name:
        raise InvalidTreeError(
            "Child name must be non-empty, not '.' or '..', and contain no '/'"
        )

    # TN-A1: Reject occupied name unless operation is replace (handled by caller)
    if name in parent._children:
        raise InvalidTreeError(f"Name '{name}' is already occupied in parent")

    # TN-A3: Reject self-links and ancestor cycles
    if child is parent:
        raise InvalidTreeError("Cannot attach a node to itself")

    # Check for ancestor cycles
    # 1. If the child is already attached, check if the parent is a descendant of the child.
    #    This means the child is an ancestor of the parent.
    if child.parent is not None:
        current = child.parent
        while current:
            if current is parent:
                raise InvalidTreeError("Cannot attach a node to one of its descendants")
            current = current.parent

    # 2. If the parent is not the root, check if the child is a descendant of the parent.
    #    This means the parent is an ancestor of the child.
    if parent is not child: # Avoid self-attachment check here, already done
        current_parent = parent
        while current_parent is not None:
            if current_parent is child: # If parent's ancestor is the child node itself
                raise InvalidTreeError("Cannot attach a node to its ancestor (cycle)")
            current_parent = current_parent.parent


    # TN-A2: If the child is already attached, detach it from its current parent first
    # This detach should only happen if it's not a self-attach or cycle attempt
    if child.parent is not None and child.parent is not parent:
        # This detach call will also clear child._parent and child._name
        child.parent.detach(child.name)
    elif child.parent is parent and child.name == name:
        # If attaching to the same parent with the same name, do nothing,
        # as it's effectively already in place.
        return

    # Attach the child and update its parent and name
    child._parent = parent
    child._name = name
    parent._children[name] = child


def detach(parent: Node, name: str) -> Node:
    # TN-A4: Report missing children
    if name not in parent._children:
        raise NodeNotFoundError(f"Child '{name}' not found in parent")

    child = parent._children.pop(name)
    child._parent = None
    child._name = None
    return child


def replace(parent: Node, name: str, child: Node) -> Node:
    # TN-A2: Attaching an already attached node moves its complete subtree
    if name in parent._children:
        old_child = parent._children[name]
        # Detach the old child before attaching the new one
        # This also handles clearing old_child's parent and name
        detach(parent, name)
    else:
        # If the name is not occupied, it's an invalid replacement target
        # although TN-A1 implies attach would raise an error here.
        # For replace, we assume the target name might not exist if we are replacing a placeholder or similar.
        # However, the test case suggests it should error if not found.
        # Let's align with TN-A4's NodeNotFoundError for missing children.
        raise NodeNotFoundError(f"Child '{name}' not found for replacement")

    # TN-A3: Reject self-links and ancestor cycles
    if child is parent:
        raise InvalidTreeError("Cannot replace with itself")
    if child.parent is not None:
        current = child.parent
        while current:
            if current is parent:
                raise InvalidTreeError("Cannot replace with a descendant")
            current = current.parent

    # TN-A2: Attach the new child and update its parent and name
    child._parent = parent
    child._name = name
    parent._children[name] = child

    # TN-A4: Return the affected node (the one that was replaced)
    return old_child


def orphan(node: Node) -> Node:
    if node.parent is None:
        # If node has no parent, it's already orphaned or is a root.
        # Detaching from None is not a valid operation in this context.
        # However, if it's the root of a tree, it's already orphaned.
        # Let's assume orphan on a root node should return itself without error.
        # If it's not a root but has no parent (e.g., detached previously),
        # we still return it as it's effectively orphaned.
        return node

    parent = node.parent
    name = node.name
    # Detach the node from its parent
    detached_node = parent.detach(name) # detach will clear parent and name on detached_node
    return detached_node

