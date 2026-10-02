from .model import Node, InvalidTreeError, NodeNotFoundError


def attach(parent: Node, name: str, child: Node) -> None:
    # TN-A1: Valid name and not occupied unless replace
    if not name or name in (".", "..") or "/" in name:
        raise InvalidTreeError(f"Invalid child name: {name}")
    if name in parent._children and child.parent is not parent:
        raise InvalidTreeError(f"Child name '{name}' already occupied")

    # TN-A3: Reject self-links and ancestor cycles
    if child is parent:
        raise InvalidTreeError("Cannot attach a node to itself")
    current = parent
    while current:
        if current is child:
            raise InvalidTreeError("Cannot attach a node to its descendant")
        current = current.parent

    # If child is already attached elsewhere, detach it first
    if child.parent and child.parent is not parent:
        # This recursive call to detach is problematic if detach is also called from Node.detach
        # For now, assume it's fine as detach is a standalone function.
        detach(child.parent, child.name)

    # TN-A2: Maintain consistent parent, name, and children
    child._parent = parent
    child._name = name
    parent._children[name] = child


def detach(parent: Node, name: str) -> Node:
    # TN-A4: Return affected node, clear detached metadata
    if name not in parent._children:
        raise NodeNotFoundError(f"Child '{name}' not found")

    child = parent._children.pop(name)
    child._parent = None
    child._name = None
    return child


def replace(parent: Node, name: str, child: Node) -> Node:
    # TN-A2: Attaching an already attached node moves its subtree
    if child.parent and child.parent is not parent:
        detach(child.parent, child.name)

    # TN-A3: Reject self-links and ancestor cycles
    if child is parent:
        raise InvalidTreeError("Cannot replace with itself")
    current = parent
    while current:
        if current is child:
            raise InvalidTreeError("Cannot replace with a descendant")
        current = current.parent

    # TN-A4: Return affected node, clear detached metadata
    old_child = parent._children.pop(name, None)
    if old_child:
        old_child._parent = None
        old_child._name = None

    child._parent = parent
    child._name = name
    parent._children[name] = child
    return old_child


def orphan(node: Node) -> Node:
    # TN-A4: Return affected node, clear detached metadata
    if node.parent:
        detach(node.parent, node.name)
    else:
        node._parent = None
        node._name = None
    return node
