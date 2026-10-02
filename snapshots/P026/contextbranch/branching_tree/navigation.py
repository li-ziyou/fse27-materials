from __future__ import annotations

from .model import InvalidTreeError, Node, NodeNotFoundError, NodePath, NotInSameTreeError


def resolve(node: Node, path: str | NodePath) -> Node:
    """Resolve a path relative to the given node."""
    if not path:
        return node

    current_node = node
    
    # If the path is already a NodePath, use its parts. Otherwise, convert string to NodePath.
    if isinstance(path, NodePath):
        path_obj = path
    else:
        path_obj = NodePath(path)
        
    path_segments = path_obj.parts

    if path_obj.is_absolute():
        # Absolute path: start from the root
        while current_node.parent is not None:
            current_node = current_node.parent
        path_segments = path_segments[1:]  # Skip the leading '/'

    for segment in path_segments:
        if segment == ".":
            continue
        elif segment == "..":
            if current_node.parent is None:
                raise NodeNotFoundError("Cannot move above the root.")
            current_node = current_node.parent
        elif segment in current_node.children:
            current_node = current_node.children[segment]
        else:
            raise NodeNotFoundError(f"Segment '{segment}' not found.")

    return current_node


def remove(node: Node, path: str | NodePath) -> Node:
    """Resolve a path, detach the node, and return it."""
    target_node = resolve(node, path)
    if target_node.parent is None and target_node.name is None:  # Check if it's the root
        raise InvalidTreeError("Cannot remove the root node.")

    parent = target_node.parent
    name = target_node.name

    if parent is None or name is None:
        # This should not happen for a node that is not the root and was resolved
        raise NodeNotFoundError("Node to remove not found in its parent's children.")

    return parent.detach(name)


def absolute_path(node: Node) -> NodePath:
    """Return the absolute path of the node."""
    if node.parent is None and node.name is None:
        return NodePath("/")  # Root node

    parts = []
    current = node
    while current.parent is not None:
        if current.name is None:
            # This indicates an inconsistent state
            raise InvalidTreeError("Node has a parent but no name.")
        parts.append(current.name)
        current = current.parent
    return NodePath("/" + "/".join(reversed(parts)))


def relative_path(node: Node, target: Node) -> NodePath:
    """Return the relative path from `node` to `target`."""
    if node is target:
        return NodePath(".")

    node_abs_path = absolute_path(node)
    target_abs_path = absolute_path(target)

    # To check if nodes are in the same tree, we can compare their root nodes.
    # If they don't have parents, they are roots of their respective trees.
    # If their parents are different, they are in different trees.
    if node.parent is not target.parent and (node.parent is None or target.parent is None):
        raise NotInSameTreeError("Cannot find relative path between nodes in different trees.")

    # If both nodes are in the same tree, proceed with path calculation.
    node_parts = node_abs_path.parts
    target_parts = target_abs_path.parts

    # Find the common ancestor
    common_len = 0
    while common_len < len(node_parts) and common_len < len(target_parts) and node_parts[common_len] == target_parts[common_len]:
        common_len += 1

    # Number of steps up from the current node to the common ancestor
    up_steps = len(node_parts) - common_len
    # The remaining parts of the target path from the common ancestor
    down_parts = target_parts[common_len:]

    relative_parts = [".."] * up_steps + list(down_parts)
    return NodePath("/".join(relative_parts))


def ancestors(node: Node) -> tuple[Node, ...]:
    """Return a tuple of ancestor nodes, from parent to root."""
    if node.parent is None:
        return ()
    
    ancestors_list = []
    current = node.parent
    while current:
        ancestors_list.append(current)
        current = current.parent
    return tuple(ancestors_list)


def descendants(node: Node) -> tuple[Node, ...]:
    """Return a tuple of descendant nodes in depth-first pre-order."""
    all_descendants = []
    
    def _traverse(current_node: Node):
        for child_name in sorted(current_node.children.keys()): # Ensure consistent order
            child = current_node.children[child_name]
            all_descendants.append(child)
            _traverse(child)

    _traverse(node)
    return tuple(all_descendants)


def siblings(node: Node) -> tuple[Node, ...]:
    """Return a tuple of sibling nodes, excluding the node itself."""
    if node.parent is None:
        return ()
    
    siblings_list = []
    # Iterate through children in sorted order for consistent results
    for name in sorted(node.parent.children.keys()):
        if name != node.name:
            siblings_list.append(node.parent.children[name])
    return tuple(siblings_list)


def leaves(node: Node) -> tuple[Node, ...]:
    """Return a tuple of leaf nodes in depth-first pre-order."""
    leaf_nodes = []
    
    def _traverse(current_node: Node):
        if not current_node.children:
            leaf_nodes.append(current_node)
            return
        
        for child_name in sorted(current_node.children.keys()): # Ensure consistent order
            child = current_node.children[child_name]
            _traverse(child)

    _traverse(node)
    return tuple(leaf_nodes)
