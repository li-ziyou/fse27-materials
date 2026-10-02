from __future__ import annotations

from .model import Node, NodePath, NodeNotFoundError, NotInSameTreeError, NotInSameTreeError


def resolve(node: Node, path: str | NodePath) -> Node:
    if not path:
        return node

    current_node = node
    path_obj = NodePath(path) if isinstance(path, str) else path

    if path_obj.is_absolute():
        # If the path is absolute, we need to start from the root of the tree.
        # We can find the root by traversing up to the node with no parent.
        while current_node.parent is not None:
            current_node = current_node.parent
        
        # If the absolute path starts with '/', remove it to match PurePosixPath behavior
        segments = path_obj.parts
        if segments[0] == '/':
            segments = segments[1:]
    else:
        segments = path_obj.parts

    for segment in segments:
        if segment == ".":
            continue
        elif segment == "..":
            if current_node.parent is None:
                # Trying to go above the root
                raise NodeNotFoundError(f"Cannot resolve path '{path}'. Movement above root is not allowed.")
            current_node = current_node.parent
        elif segment in current_node._children:
            current_node = current_node._children[segment]
        else:
            raise NodeNotFoundError(f"Cannot resolve path '{path}'. Segment '{segment}' not found.")

    return current_node


def remove(node: Node, path: str | NodePath) -> Node:
    # Resolve the path to the node to be removed
    target_node = resolve(node, path)

    # Refuse to remove the root node
    if target_node.parent is None and target_node.name is None:
        raise InvalidTreeError("Cannot remove the root node.")

    # Detach the subtree from its parent
    return detach(target_node.parent, target_node.name)


def absolute_path(node: Node) -> NodePath:
    if node.parent is None and node.name is None:
        return NodePath("/")

    path_parts = []
    current = node
    while current.parent is not None:
        path_parts.append(current.name)
        current = current.parent
    
    # Reverse the parts to get the path from root to node
    path_parts.reverse()
    return NodePath("/" + "/".join(path_parts))


def relative_path(node: Node, target: Node) -> NodePath:
    # Handle the case where both nodes are the root of their respective trees
    if node.parent is None and target.parent is None:
        if node is target:
            return NodePath(".") # Same root node
        else:
            # Different root nodes, thus different trees
            raise NotInSameTreeError("Cannot determine relative path between nodes in different trees.")

    node_path_parts = absolute_path(node).parts
    target_path_parts = absolute_path(target).parts

    # Check if they are in the same tree by comparing the root
    # Check if they are in the same tree
    def get_root(n: Node) -> Node:
        while n.parent is not None:
            n = n.parent
        return n

    node_root = get_root(node)
    target_root = get_root(target)

    if node_root is not target_root:
        raise NotInSameTreeError("Cannot determine relative path between nodes in different trees.")

    # Find the first differing segment
    common_len = 0
    min_len = min(len(node_path_parts), len(target_path_parts))
    while common_len < min_len and node_path_parts[common_len] == target_path_parts[common_len]:
        common_len += 1

    # Number of '..' needed to go up from node to the common ancestor
    up_segments = len(node_path_parts) - common_len
    
    # Segments to go down from the common ancestor to the target
    down_segments = target_path_parts[common_len:]

    relative_parts = [".."] * up_segments + list(down_segments)

    if not relative_parts:
        return NodePath(".")
    
    return NodePath("/".join(relative_parts))


def ancestors(node: Node) -> tuple[Node, ...]:
    if node.parent is None:
        return ()
    return (node.parent,) + ancestors(node.parent)


def descendants(node: Node) -> tuple[Node, ...]:
    # Depth-first pre-order traversal
    nodes = []
    for child in node.children.values():
        nodes.append(child)
        nodes.extend(descendants(child))
    return tuple(nodes)


def siblings(node: Node) -> tuple[Node, ...]:
    if node.parent is None:
        return ()
    
    # Return siblings in insertion order
    return tuple(sibling for sibling in node.parent.children.values() if sibling is not node)


def leaves(node: Node) -> tuple[Node, ...]:
    # Depth-first traversal to find leaves
    nodes = []
    if not node.children:
        return (node,)
    
    for child in node.children.values():
        nodes.extend(leaves(child))
    return tuple(nodes)
