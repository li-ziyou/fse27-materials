from __future__ import annotations

from .model import Node, NodePath, NodeNotFoundError, InvalidTreeError, NotInSameTreeError



def resolve(node: Node, path: str | NodePath) -> Node:
    """
    Resolves a path relative to the given node.
    Supports absolute paths, relative paths, '.', and '..'.
    Raises NodeNotFoundError if path segments are invalid or if moving above root.
    """
    if isinstance(path, str):
        path = NodePath(path)

    current_node = node
    path_segments = list(path.parts)

    # If the path is absolute, start from the root.
    if path.is_absolute():
        # Find the root of the current node
        root = node
        while root.parent is not None:
            root = root.parent
        current_node = root
        # Remove the leading '/' from the path segments if present
        if path_segments and path_segments[0] == '/':
            path_segments = path_segments[1:]

    for segment in path_segments:
        if segment == ".":
            continue  # Stay at the current node
        elif segment == "..":
            if current_node.parent is None:
                # Attempting to go above the root
                raise NodeNotFoundError(f"Cannot resolve path '{path}': attempted to move above root.")
            current_node = current_node.parent
        else:
            # Navigate to a child
            if segment not in current_node.children:
                raise NodeNotFoundError(f"Cannot resolve path '{path}': segment '{segment}' not found.")
            current_node = current_node.children[segment]

    return current_node


def remove(node: Node, path: str | NodePath) -> Node:
    """
    Resolves a path, detaches the subtree at that path, and returns the detached node.
    Refuses to remove the root node.
    """
    # Resolve the path to find the node to remove.
    try:
        target_node = resolve(node, path)
    except NodeNotFoundError:
        raise

    # TN-B2: Refuses to remove the root.
    if target_node.parent is None:
        raise InvalidTreeError("Cannot remove the root node.")

    # Detach the node from its parent. The detach method should handle clearing parent/name.
    # We need to call detach on the parent of the target_node.
    parent_of_target = target_node.parent
    if parent_of_target is None: # Should not happen if target_node is not root
        raise InvalidTreeError("Internal error: target node has no parent but is not root.")

    detached_node = parent_of_target.detach(target_node.name)
    return detached_node


def absolute_path(node: Node) -> NodePath:
    """
    Returns the absolute path of the node.
    """
    path_segments = []
    current = node
    while current.parent is not None:
        if current.name is None:
            # This should ideally not happen in a valid tree structure after initialisation
            raise InvalidTreeError("Node in tree has no name.")
        path_segments.append(current.name)
        current = current.parent
    
    # The segments are collected from child to parent, so reverse them.
    # Prepend '/' for an absolute path.
    return NodePath("/" + "/".join(reversed(path_segments)))


def relative_path(node: Node, target: Node) -> NodePath:
    """
    Returns the relative path from `node` to `target`.
    Raises NotInSameTreeError if nodes are not in the same tree.
    """
    if node is target:
        return NodePath(".")

    # Helper to find the root of a node
    def get_root(n: Node) -> Node:
        while n.parent is not None:
            n = n.parent
        return n

    if get_root(node) is not get_root(target):
        raise NotInSameTreeError("Target node is not in the same tree as the current node.")

    # Get ancestors for both nodes, including themselves
    node_ancestors = list(node.ancestors) + [node]
    target_ancestors = list(target.ancestors) + [target]

    # Find the deepest common ancestor
    common_ancestor_index = 0
    # Iterate from the root upwards to find the last common ancestor
    while common_ancestor_index < min(len(node_ancestors), len(target_ancestors)):
        if node_ancestors[common_ancestor_index] is target_ancestors[common_ancestor_index]:
            common_ancestor_index += 1
        else:
            break
    # The common ancestor is the node *before* the index where they diverged
    common_ancestor = node_ancestors[common_ancestor_index - 1]

    # Construct the relative path
    # Go up from the current node to the common ancestor
    path_segments = [".."] * (len(node_ancestors) - common_ancestor_index)

    # Go down from the common ancestor to the target node
    # We need to find the path from the common ancestor to the target.
    # The target_ancestors list contains the target and its ancestors.
    # We need the part of target_ancestors that starts *after* the common ancestor.
    # The index of the common ancestor in target_ancestors is common_ancestor_index - 1.
    # So we need segments from target_ancestors[common_ancestor_index] onwards.
    path_segments.extend(target.name for target in target_ancestors[common_ancestor_index:])

    # Ensure all path segments are strings before joining
    return NodePath("/".join(str(segment) for segment in path_segments))


def ancestors(node: Node) -> tuple[Node, ...]:
    """
    Returns a tuple of the node's ancestors, from parent to root.
    """
    ancestors_list = []
    current = node.parent
    while current is not None:
        ancestors_list.append(current)
        current = current.parent
    return tuple(ancestors_list)


def descendants(node: Node) -> tuple[Node, ...]:
    """
    Returns a tuple of all descendants in depth-first pre-order.
    """
    descendants_list = []
    nodes_to_visit = list(node.children.values())
    while nodes_to_visit:
        current_node = nodes_to_visit.pop(0)
        descendants_list.append(current_node)
        # Add children to the front of the list for pre-order traversal
        nodes_to_visit = list(current_node.children.values()) + nodes_to_visit
    return tuple(descendants_list)


def siblings(node: Node) -> tuple[Node, ...]:
    """
    Returns a tuple of the node's siblings, in insertion order.
    """
    if node.parent is None:
        return ()
    # The order of keys in `parent._children` is insertion order
    return tuple(child for child in node.parent.children.values() if child is not node)


def leaves(node: Node) -> tuple[Node, ...]:
    """
    Returns a tuple of all leaf nodes in depth-first order.
    A leaf node is a node with no children.
    """
    leaf_nodes = []
    nodes_to_visit = [node]  # Start with the current node
    while nodes_to_visit:
        current_node = nodes_to_visit.pop(0)
        if not current_node.children:
            leaf_nodes.append(current_node)
        else:
            # Add children to the front of the list for depth-first traversal
            nodes_to_visit = list(current_node.children.values()) + nodes_to_visit
    return tuple(leaf_nodes)
