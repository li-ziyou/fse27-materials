from __future__ import annotations

from .model import Node, NodePath, NodeNotFoundError, NotInSameTreeError


def resolve(node: Node, path: str | NodePath) -> Node:
    if not isinstance(path, NodePath):
        path = NodePath(path)

    if path.is_absolute():
        # Traverse from the root of the tree
        current = node
        while current.parent is not None:
            current = current.parent
    else:
        current = node

    if path == NodePath("."):
        return current

    # Handle ".."
    if path == NodePath(".."):
        if current.parent is None:
            raise NodeNotFoundError(f"Cannot move above root: {path}")
        return current.parent

    # Traverse the path
    segments = path.parts
    if path.is_absolute():
        segments = segments[1:]  # Skip the leading '/' for absolute paths

    for segment in segments:
        if segment == ".":
            # Stay in the current directory
            continue
        elif segment == "..":
            # Move up to the parent directory
            if current.parent is None:
                raise NodeNotFoundError(f"Cannot move above root: {path}")
            current = current.parent
        else:
            # Traverse to the child segment
            if segment not in current.children:
                raise NodeNotFoundError(f"Path segment '{segment}' not found in {current.path if current.path else '/'}")
            current = current.children[segment]

    return current


def remove(node: Node, path: str | NodePath) -> Node:
    target_node = resolve(node, path)
    if target_node.parent is None:
        # Cannot remove the root node
        raise NodeNotFoundError("Cannot remove the root node.")

    # Detach the target node from its parent
    detached_node = target_node.parent.detach(target_node.name)
    return detached_node


def absolute_path(node: Node) -> NodePath:
    if node.parent is None:
        return NodePath("/")
    
    path_parts = []
    current = node
    while current.parent is not None:
        path_parts.append(current.name)
        current = current.parent
    
    path_parts.reverse()
    return NodePath("/" + "/".join(path_parts))


def relative_path(node: Node, target: Node) -> NodePath:
    # Determine the root of the current node and the target node
    node_root = node
    while node_root.parent is not None:
        node_root = node_root.parent

    target_root = target
    while target_root.parent is not None:
        target_root = target_root.parent

    if node_root != target_root:
        raise NotInSameTreeError("Cannot determine relative path between nodes in different trees.")

    node_path_parts = node.path.parts
    target_path_parts = target.path.parts

    # Find the common ancestor
    common_len = 0
    min_len = min(len(node_path_parts), len(target_path_parts))
    while common_len < min_len and node_path_parts[common_len] == target_path_parts[common_len]:
        common_len += 1

    # Construct the relative path
    # Number of steps up from 'node' to the common ancestor
    steps_up = len(node_path_parts) - common_len
    relative_parts = [".."] * steps_up
    # Segments from the common ancestor to 'target'
    relative_parts.extend(target_path_parts[common_len:])

    return NodePath("/".join(relative_parts))


def ancestors(node: Node) -> tuple[Node, ...]:
    if node.parent is None:
        return ()
    
    ancestor_list = []
    current = node.parent
    while current is not None:
        ancestor_list.append(current)
        current = current.parent
    return tuple(ancestor_list)


def descendants(node: Node) -> tuple[Node, ...]:
    nodes = []
    
    def _traverse(current_node):
        for child_name, child_node in current_node.children.items():
            nodes.append(child_node)
            _traverse(child_node)
            
    _traverse(node)
    return tuple(nodes)


def siblings(node: Node) -> tuple[Node, ...]:
    if node.parent is None:
        return ()  # Root node has no siblings
    
    return tuple(
        child for name, child in node.parent.children.items() if child is not node
    )


def leaves(node: Node) -> tuple[Node, ...]:
    leaf_nodes = []
    
    def _traverse(current_node):
        if not current_node.children:
            leaf_nodes.append(current_node)
            return
            
        for child_name, child_node in current_node.children.items():
            _traverse(child_node)
            
    _traverse(node)
    return tuple(leaf_nodes)
