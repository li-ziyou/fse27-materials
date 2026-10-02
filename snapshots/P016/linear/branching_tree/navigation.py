from __future__ import annotations

from .model import Node, NodePath, NodeNotFoundError, NotInSameTreeError


def resolve(node: Node, path: str | NodePath) -> Node:
    if not path:
        return node

    current_node = node
    path_obj = NodePath(path)

    if path_obj.is_absolute():
        # If the path is absolute, we need to start from the root of the tree.
        # We can find the root by repeatedly going up the parent chain.
        while current_node.parent is not None:
            current_node = current_node.parent
        path_segments = path_obj.parts[1:]  # Skip the leading '/'
    else:
        path_segments = path_obj.parts

    for segment in path_segments:
        if segment == ".":
            continue
        elif segment == "..":
            if current_node.parent is None:
                raise NodeNotFoundError("Cannot move above the root node")
            current_node = current_node.parent
        elif segment in current_node._children:
            current_node = current_node._children[segment]
        else:
            raise NodeNotFoundError(f"Segment '{segment}' not found in path")

    return current_node


def remove(node: Node, path: str | NodePath) -> Node:
    target_node = resolve(node, path)

    if target_node.parent is None and target_node._children:
        raise InvalidTreeError("Cannot remove the root node if it has children.")
    if target_node.parent is None:  # It's the root and has no children
        raise NodeNotFoundError("Cannot remove the root node.")

    # Detach the target node from its parent
    parent = target_node.parent
    if parent._children.get(target_node.name) is target_node:
        # Use the detach function from structure.py
        from .structure import detach
        return detach(parent, target_node.name)
    else:
        # This case should ideally not happen if resolve is correct
        raise NodeNotFoundError("Target node not found under its resolved parent.")


def absolute_path(node: Node) -> NodePath:
    if node.parent is None:
        return NodePath("/")

    path_parts = []
    current = node
    while current.parent is not None:
        path_parts.append(current.name)
        current = current.parent

    # Reverse the parts and join them with '/'
    return NodePath("/" + "/".join(reversed(path_parts)))


def relative_path(node: Node, target: Node) -> NodePath:
    if node is target:
        return NodePath(".")

    # Check if nodes are in the same tree by comparing their roots.
    # This assumes Node.root is correctly implemented.
    try:
        if node.root is not target.root:
            raise NotInSameTreeError("Nodes are not in the same tree.")
    except NodeNotFoundError:
        # If either node is not properly attached to a tree (e.g., orphaned),
        # we can't determine their relative path.
        raise NotInSameTreeError("One or both nodes are not attached to a tree.")

    # Find the lowest common ancestor (LCA)
    node_ancestors_set = {ancestor for ancestor in node.ancestors}
    target_ancestors_set = {ancestor for ancestor in target.ancestors}

    common_ancestor = None
    # Check ancestors of 'node' to find the first one that is also an ancestor of 'target'
    for ancestor in node.ancestors:
        if ancestor in target_ancestors_set:
            common_ancestor = ancestor
            break

    # If no common ancestor found among node's ancestors, check if target is an ancestor of node
    if common_ancestor is None and target in node_ancestors_set:
        common_ancestor = target
    # Or if node is an ancestor of target
    elif common_ancestor is None and node in target_ancestors_set:
        common_ancestor = node
    # If still no common ancestor, and they are in the same tree, their parent must be the LCA
    elif common_ancestor is None and node.parent is not None and node.parent == target.parent:
         common_ancestor = node.parent
    # If one is the root and the other is not, the root is the common ancestor
    elif common_ancestor is None and node.root is node and target.parent is not None:
        common_ancestor = node
    elif common_ancestor is None and target.root is target and node.parent is not None:
        common_ancestor = target
    # If both are roots and not the same node, they are in different trees (already caught by root check, but for completeness)
    elif common_ancestor is None and node.parent is None and target.parent is None:
        raise NotInSameTreeError("Nodes are not in the same tree (both roots but different).")

    if common_ancestor is None:
        # This should ideally not be reached if the root check is comprehensive,
        # but as a safeguard:
        raise NotInSameTreeError("Could not determine common ancestor, nodes may be in different trees.")

    # Calculate the path from 'node' up to the common ancestor
    path_up = []
    current = node
    while current is not common_ancestor:
        if current.parent is None:
            # This should not happen if common_ancestor is correctly identified and they are in the same tree
            raise NotInSameTreeError("Path calculation error: node has no parent but not at common ancestor.")
        path_up.append("..")
        current = current.parent

    # Calculate the path from the common ancestor down to the 'target'
    path_down = []
    current = target
    while current is not common_ancestor:
        if current.parent is None:
            # This should not happen if common_ancestor is correctly identified and they are in the same tree
            raise NotInSameTreeError("Path calculation error: target has no parent but not at common ancestor.")
        path_down.append(current.name)
        current = current.parent

    # Combine the paths: go up to the LCA, then down to the target
    relative_parts = path_up + list(reversed(path_down))
    return NodePath("/".join(relative_parts))


    # Calculate the path from node up to the common ancestor
    path_up = []
    current = node
    while current is not common_ancestor:
        if current.parent is None:
             raise NotInSameTreeError("Path calculation error: node has no parent but not at common ancestor.")
        path_up.append("..")
        current = current.parent

    # Calculate the path from the common ancestor down to the target
    path_down = []
    current = target
    while current is not common_ancestor:
        if current.parent is None:
            raise NotInSameTreeError("Path calculation error: target has no parent but not at common ancestor.")
        path_down.append(current.name)
        current = current.parent

    # Combine the paths
    relative_parts = path_up + list(reversed(path_down))
    return NodePath("/".join(relative_parts))


@property
def root(self: Node) -> Node:
    current = self
    while current.parent is not None:
        current = current.parent
    return current
Node.root = root # type: ignore


def ancestors(node: Node) -> tuple[Node, ...]:
    if node.parent is None:
        return ()

    ancestors_list = []
    current = node.parent
    while current is not None:
        ancestors_list.append(current)
        current = current.parent
    return tuple(ancestors_list)
# Removed the assignment: Node.ancestors = ancestors # type: ignore


def descendants(node: Node) -> tuple[Node, ...]:
    # Depth-first pre-order traversal
    desc_list = []
    for child_name, child_node in node._children.items():
        desc_list.append(child_node)
        desc_list.extend(descendants(child_node))
    return tuple(desc_list)
# Removed the assignment: Node.descendants = descendants # type: ignore


def siblings(node: Node) -> tuple[Node, ...]:
    if node.parent is None:
        return ()

    parent = node.parent
    # Get the parent's children mapping.
    parent_children = parent.children

    sibling_nodes = []
    for name, child in parent_children.items():
        # We want all children of the parent that are NOT the node itself.
        if child is not node:
            sibling_nodes.append(child)

    # The test expects a specific tuple of siblings.
    # If the issue is with object identity due to resolve(),
    # this direct iteration should return the correct instances from the tree.
    return tuple(sibling_nodes)
#Node.siblings = siblings # type: ignore


def leaves(node: Node) -> tuple[Node, ...]:
    # Depth-first traversal to find leaves
    leaf_list = []
    if not node._children:
        leaf_list.append(node)
        return tuple(leaf_list)

    for child_name, child_node in node._children.items():
        leaf_list.extend(leaves(child_node))
    return tuple(leaf_list)

# Node.leaves = leaves # type: ignore