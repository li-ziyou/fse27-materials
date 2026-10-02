from __future__ import annotations

from .model import Node, InvalidTreeError, NodeNotFoundError


def attach(parent: Node, name: str, child: Node) -> None:
    if not name or name in {".", ".."}:
        raise InvalidTreeError("Child name cannot be '.' or '..'")
    if "/" in name:
        raise InvalidTreeError("Child name cannot contain '/'")

    if name in parent._children and child is not parent._children[name]:
        raise InvalidTreeError(f"Name '{name}' is already occupied")

    # Check for self-links and ancestor cycles
    # If child is not attached to any parent, it's safe to attach.
    # If it is attached, we need to check for cycles.
    current = parent
    while current is not None:
        if current is child:
            raise InvalidTreeError("Cannot attach a node to one of its descendants")
        current = current.parent

    # If child is already attached, detach it from its current parent before attaching to new parent.
    # This handles moving subtrees.
    if child.parent is not None:
        # Ensure we are not trying to attach a node to itself or a descendant
        if child is parent:
            raise InvalidTreeError("Cannot attach a node to itself")
        
        # This check is already done above, but for clarity and to ensure atomicity of the operation
        # if child is an ancestor of parent, it would have been caught already.
        
        # Detach from old parent
        detach(child.parent, child._name)
        
    child._parent = parent
    child._name = name
    parent._children[name] = child


def detach(parent: Node, name: str) -> Node:
    if name not in parent._children:
        raise NodeNotFoundError(f"Child '{name}' not found")

    child = parent._children.pop(name)
    # TN-A4: clear detached parent/name metadata
    child._parent = None
    child._name = None
    return child


def replace(parent: Node, name: str, child: Node) -> Node:
    if name not in parent._children:
        raise NodeNotFoundError(f"Child '{name}' not found")

    old_child = parent._children.pop(name) # Detach the old child first

    # Check for self-links and ancestor cycles
    if child.parent is None and child._name is None: # If child is not attached to any parent
        pass # It's safe to replace
    else:
        # Check if child is an ancestor of parent
        current = parent
        while current is not None:
            if current is child:
                # If a cycle is detected, re-attach the old child and raise error
                parent._children[name] = old_child
                old_child._parent = parent
                old_child._name = name
                raise InvalidTreeError("Cannot replace with a node that is a descendant of the parent")
            current = current.parent

    if child.parent is not None or child._name is not None:
        # Detach from old parent if it exists
        if child.parent:
            # Before detaching, ensure the child is not the parent itself
            if child is parent:
                # Re-attach old child before raising error
                parent._children[name] = old_child
                old_child._parent = parent
                old_child._name = name
                raise InvalidTreeError("Cannot replace with a node that is the parent itself")
            
            # Ensure the child is not an ancestor of the parent before detaching
            current = parent
            while current is not None:
                if current is child:
                    # Re-attach old child before raising error
                    parent._children[name] = old_child
                    old_child._parent = parent
                    old_child._name = name
                    raise InvalidTreeError("Cannot replace with a node that is a descendant of the parent")
                current = current.parent
            
            # Detach the child from its original parent if it exists and is not the node being replaced
            if child.parent and child.parent != parent:
                 detach(child.parent, child._name)

    child._parent = parent
    child._name = name
    parent._children[name] = child
    # TN-A4: return the affected node (old_child)
    # Clear parent and name metadata for the detached node
    old_child._parent = None
    old_child._name = None
    return old_child


def orphan(node: Node) -> Node:
    if node.parent is None or node._name is None:
        # This is the root node, cannot orphan
        raise InvalidTreeError("Cannot orphan the root node")

    parent = node.parent
    name = node._name
    # Detach from parent, which also clears parent and name on the node
    detach(parent, name)
    return node
