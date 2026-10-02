from __future__ import annotations

from .model import Node, NodePath, NodeNotFoundError, NotInSameTreeError, InvalidTreeError


def resolve(node: Node, path: str | NodePath) -> Node:
    """
    TN-B1: resolve supports absolute and relative NodePath values, including '.' and '..',
    and raises NodeNotFoundError for missing segments or movement above the root.
    """
    if not path:
        return node

    current_node = node
    path_obj = NodePath(path)

    if path_obj.is_absolute():
        # If the path is absolute, we need to start from the root of the tree.
        # Assuming root is the node with no parent.
        while current_node.parent is not None:
            current_node = current_node.parent
        segments = path_obj.parts[1:]  # Skip the leading '/'
    else:
        segments = path_obj.parts

    for segment in segments:
        if segment == ".":
            continue
        elif segment == "..":
            if current_node.parent is None:
                raise NodeNotFoundError("Cannot move above the root node")
            current_node = current_node.parent
        else:
            if segment not in current_node.children:
                raise NodeNotFoundError(f"Segment '{segment}' not found")
            current_node = current_node.children[segment]
    return current_node


def remove(node: Node, path: str | NodePath) -> Node:
    """
    TN-B2: remove resolves a path, detaches that complete subtree, and refuses to remove the root.
    """
    if node.path == NodePath(path) and node.parent is None:
        raise InvalidTreeError("Cannot remove the root node")

    target_node = resolve(node, path)
    if target_node.parent is None:  # This should be the root node, already checked
        raise InvalidTreeError("Cannot remove the root node")

    # Detach the node. The detach function in structure.py handles clearing parent/name.
    # We need to get the parent of the target node first.
    parent_of_target = target_node.parent
    if parent_of_target is None:
        # This case should ideally not be reached due to the root check above.
        raise NodeNotFoundError("Target node has no parent to detach from.")

    return parent_of_target.detach(target_node.name)


def absolute_path(node: Node) -> NodePath:
    """
    TN-B3: path returns an absolute path.
    """
    if node.parent is None:
        return NodePath("/")
    
    path_parts = []
    current = node
    while current.parent is not None:
        if current.name is None:
            # This indicates an inconsistent state, should not happen in a valid tree
            raise InvalidTreeError("Node has a parent but no name.")
        path_parts.append(current.name)
        current = current.parent
    
    return NodePath("/" + "/".join(reversed(path_parts)))


def relative_path(node: Node, target: Node) -> NodePath:
    """
    TN-B3: relative_path_to returns a correct relative path for nodes in the same tree;
    separate trees raise NotInSameTreeError.
    """
    if node is target:
        return NodePath(".")

    # Check if they are in the same tree by traversing up from both nodes
    node_ancestors = {node.path} if node.path else set()
    current = node.parent
    while current:
        node_ancestors.add(current.path)
        current = current.parent

    target_ancestors = {target.path} if target.path else set()
    current = target.parent
    while current:
        target_ancestors.add(current.path)
        current = current.parent

    # If the root nodes are different, they are in different trees
    root_node = node
    while root_node.parent is not None:
        root_node = root_node.parent
    
    target_root_node = target
    while target_root_node.parent is not None:
        target_root_node = target_root_node.parent

    if root_node is not target_root_node:
        raise NotInSameTreeError("Nodes are not in the same tree")

    # Find the lowest common ancestor
    common_ancestor = None
    node_path_parts = absolute_path(node).parts
    target_path_parts = absolute_path(target).parts

    min_len = min(len(node_path_parts), len(target_path_parts))
    for i in range(min_len):
        if node_path_parts[i] == target_path_parts[i]:
            common_ancestor = node.resolve(NodePath("/" + "/".join(node_path_parts[:i+1])))
        else:
            break

    if common_ancestor is None:
        # This should not happen if they are in the same tree and not the same node
        # It implies they are not in the same tree, which should have been caught.
        # Or one is root and other is not.
        # If one is root, common ancestor is root.
        if node.parent is None: common_ancestor = node
        elif target.parent is None: common_ancestor = target
        else:
             raise NotInSameTreeError("Could not find common ancestor, likely different trees.")


    # Calculate relative path
    # Number of steps up from 'node' to 'common_ancestor'
    steps_up = len(absolute_path(node).parts) - len(absolute_path(common_ancestor).parts)
    
    # Path from 'common_ancestor' to 'target'
    target_path_segments = absolute_path(target).parts[len(absolute_path(common_ancestor).parts):]

    relative_parts = [".."] * steps_up + list(target_path_segments)
    
    return NodePath("/".join(relative_parts))


def ancestors(node: Node) -> tuple[Node, ...]:
    """
    TN-B4: ancestors reflect the current tree and return tuples.
    """
    anc = []
    current = node.parent
    while current is not None:
        anc.append(current)
        current = current.parent
    return tuple(anc)


def descendants(node: Node) -> tuple[Node, ...]:
    """
    TN-B4: depth-first pre-order descendants reflect the current tree and return tuples.
    """
    desc = []
    
    def dfs(current_node: Node):
        for child_name, child_node in current_node.children.items():
            desc.append(child_node)
            dfs(child_node)

    dfs(node)
    return tuple(desc)


def siblings(node: Node) -> tuple[Node, ...]:
    """
    TN-B4: insertion-ordered siblings reflect the current tree and return tuples.
    """
    if node.parent is None:
        return ()  # Root node has no siblings

    # Ensure the order of siblings is consistent with the order in the parent's children dictionary
    # which is insertion-ordered in Python 3.7+
    # Filter out the node itself from its siblings list.
    return tuple(child for child in node.parent.children.values() if child is not node)

    # The children dictionary preserves insertion order in Python 3.7+
    return tuple(node.parent.children.values())


def leaves(node: Node) -> tuple[Node, ...]:
    """
    TN-B4: depth-first leaves reflect the current tree and return tuples.
    """
    leaf_nodes = []
    
    def dfs(current_node: Node):
        if not current_node.children:
            leaf_nodes.append(current_node)
            return
        
        for child_name, child_node in current_node.children.items():
            dfs(child_node)

    dfs(node)
    return tuple(leaf_nodes)
