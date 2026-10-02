from __future__ import annotations

from .model import Node, NodePath, NodeNotFoundError, NotInSameTreeError


def resolve(node: Node, path: str | NodePath) -> Node:
    """TN-B1: Resolve a path (absolute or relative) to a node."""
    if isinstance(path, str):
        path = NodePath(path)
    
    parts = path.parts
    current = node
    
    # Handle absolute paths (starting with /)
    if path.is_absolute():
        # Find the root
        while current._parent is not None:
            current = current._parent
        # Remove leading empty string from absolute path
        parts = parts[1:]
    
    # Navigate through the parts
    for part in parts:
        if part == ".":
            continue
        elif part == "..":
            if current._parent is None:
                raise NodeNotFoundError("Cannot move above root")
            current = current._parent
        else:
            if part not in current._children:
                raise NodeNotFoundError(f"Child '{part}' not found at path")
            current = current._children[part]
    
    return current


def remove(node: Node, path: str | NodePath) -> Node:
    """TN-B2: Detach and return the node at a path."""
    target = resolve(node, path)
    
    # Cannot remove the root
    if target._parent is None:
        raise ValueError("Cannot remove the root node")
    
    parent = target._parent
    name = target._name
    return parent.detach(name)


def absolute_path(node: Node) -> NodePath:
    """TN-B3: Return this node's absolute path."""
    parts = []
    current = node
    while current._parent is not None:
        parts.append(current._name)
        current = current._parent
    
    path_str = "/" + "/".join(reversed(parts))
    return NodePath(path_str)


def relative_path(node: Node, target: Node) -> NodePath:
    """TN-B3: Return a relative path from node to target in the same tree."""
    # Check if nodes are in the same tree
    node_root = node
    while node_root._parent is not None:
        node_root = node_root._parent
    
    target_root = target
    while target_root._parent is not None:
        target_root = target_root._parent
    
    if node_root is not target_root:
        raise NotInSameTreeError("Nodes are not in the same tree")
    
    # Get absolute paths
    node_parts = []
    current = node
    while current._parent is not None:
        node_parts.append(current._name)
        current = current._parent
    node_parts.reverse()
    
    target_parts = []
    current = target
    while current._parent is not None:
        target_parts.append(current._name)
        current = current._parent
    target_parts.reverse()
    
    # Find common ancestor
    i = 0
    while i < len(node_parts) and i < len(target_parts) and node_parts[i] == target_parts[i]:
        i += 1
    
    # Build relative path
    ups = len(node_parts) - i
    downs = target_parts[i:]
    
    parts = [".."] * ups + downs
    if not parts:
        return NodePath(".")
    
    return NodePath("/".join(parts))


def ancestors(node: Node) -> tuple[Node, ...]:
    """TN-B4: Return tuples of ancestor nodes."""
    result = []
    current = node._parent
    while current is not None:
        result.append(current)
        current = current._parent
    return tuple(result)


def descendants(node: Node) -> tuple[Node, ...]:
    """TN-B4: Return depth-first pre-order descendants."""
    result = []
    
    def traverse(n: Node) -> None:
        for child in n._children.values():
            result.append(child)
            traverse(child)
    
    traverse(node)
    return tuple(result)


def siblings(node: Node) -> tuple[Node, ...]:
    """TN-B4: Return insertion-ordered siblings."""
    if node._parent is None:
        return ()
    
    parent = node._parent
    result = []
    for child_name, child in parent._children.items():
        if child is not node:
            result.append(child)
    
    return tuple(result)


def leaves(node: Node) -> tuple[Node, ...]:
    """TN-B4: Return depth-first leaf nodes."""
    result = []
    
    def traverse(n: Node) -> None:
        if not n._children:
            result.append(n)
        else:
            for child in n._children.values():
                traverse(child)
    
    traverse(node)
    return tuple(result)
