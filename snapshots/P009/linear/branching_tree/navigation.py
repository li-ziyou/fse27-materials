from __future__ import annotations

from .model import Node, NodePath, NodeNotFoundError, InvalidTreeError


def resolve(node: Node, path: str | NodePath) -> Node:
    """
    Resolve a path to a node.

    TN-B1: Supports absolute and relative NodePath values, including '.' and '..'.
           Raises NodeNotFoundError for missing segments or movement above the root.
    """
        if not isinstance(path, NodePath):
            path = NodePath(path)

        # If the path is absolute, start from the root
        if path.is_absolute():
            # Find the actual root by traversing up
            temp_node = node
            while temp_node.parent is not None:
                temp_node = temp_node.parent
            current_node = temp_node
            # Skip the first '/' part if it exists, as it's the root indicator
            segments_to_traverse = list(path.parts)
            if segments_to_traverse and segments_to_traverse[0] == '/':
                segments_to_traverse = segments_to_traverse[1:]
        else:
            current_node = node
            segments_to_traverse = list(path.parts)

        # Traverse the path segments
        for segment in segments_to_traverse:
            if segment == ".":
                continue  # Stay at the current node
            elif segment == "..":
                if current_node.parent is None:
                    raise NodeNotFoundError("Cannot resolve path above the root.")
                current_node = current_node.parent
            else:
                if segment not in current_node.children:
                    raise NodeNotFoundError(f"Segment '{segment}' not found in path.")
                current_node = current_node.children[segment]

        return current_node


def remove(node: Node, path: str | NodePath) -> Node:
    """
    Resolve a path, detach that complete subtree, and refuse to remove the root.

    TN-B2: Resolves a path, detaches that complete subtree, and refuses to remove the root.
    """
    resolved_node = node.resolve(path)

    # TN-B2: Refuse to remove the root
    if resolved_node.parent is None:
        raise InvalidTreeError("Cannot remove the root node.")

    # Detach the resolved node
    # The detach method will handle clearing parent/name and removing from parent's children
    return resolved_node.orphan()


def absolute_path(node: Node) -> NodePath:
    """
    Return this node's absolute NodePath.

    TN-B3: Returns an absolute path.
    """
    parts = []
    current = node
    while current.parent is not None:
        # Ensure name is not None before appending
        if current.name is not None:
            parts.append(current.name)
        else:
            # This case should ideally not happen for a node within a tree
            # unless it's an orphaned node that hasn't been properly reset.
            # For robustness, we might want to raise an error or handle it.
            # For now, we'll assume valid tree structure.
            pass
        current = current.parent

    # The parts are collected from child to parent, so reverse them
    parts.reverse()
    # NodePath expects a leading '/' for absolute paths
    return NodePath("/" + "/".join(parts))


def relative_path(node: Node, target: Node) -> NodePath:
    """
    Return a relative NodePath from this node to the target node.

    TN-B3: Returns a correct relative path for nodes in the same tree;
           separate trees raise NotInSameTreeError.
    """
    if node.path.root != target.path.root:
        raise NotInSameTreeError("Cannot get relative path between nodes in different trees.")

    node_parts = node.path.parts
    target_parts = target.path.parts

    # Find the length of the common prefix
    common_len = 0
    min_len = min(len(node_parts), len(target_parts))
    while common_len < min_len and node_parts[common_len] == target_parts[common_len]:
        common_len += 1

    # Number of steps up from 'node' to the common ancestor
    steps_up = len(node_parts) - common_len
    # Segments down from the common ancestor to 'target'
    steps_down = target_parts[common_len:]

    # Construct the relative path
    relative_parts = [".."] * steps_up + list(steps_down)

    return NodePath("/".join(relative_parts))


def ancestors(node: Node) -> tuple[Node, ...]:
    if node.parent is None:
        return ()
    return (node.parent,) + ancestors(node.parent)


def descendants(node: Node) -> tuple[Node, ...]:
    """Depth-first pre-order traversal of descendants."""
    result = []
    for child_name, child_node in node.children.items():
        result.append(child_node)
        result.extend(descendants(child_node))
    return tuple(result)


def siblings(node: Node) -> tuple[Node, ...]:
    if node.parent is None:
        return ()
    # Get all children of the parent, then filter out the node itself.
    # The order should be insertion order, which dict preserves.
    return tuple(child for child in node.parent.children.values() if child is not node)


def leaves(node: Node) -> tuple[Node, ...]:
    """Depth-first traversal to find all leaf nodes."""
    result = []
    if not node.children:  # If the node itself is a leaf
        return (node,)

    for child_name, child_node in node.children.items():
        result.extend(leaves(child_node))
    return tuple(result)
