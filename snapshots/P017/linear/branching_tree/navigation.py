from __future__ import annotations

from .model import Node, NodePath, NodeNotFoundError, InvalidTreeError, NotInSameTreeError


def resolve(node: Node, path: str | NodePath) -> Node:
    if not isinstance(path, NodePath):
        path = NodePath(path)

    segments = path.parts

    # Handle absolute path
    if path.is_absolute():
        current = node
        # Traverse up to find the root
        while current.parent is not None:
            current = current.parent
        # If the path is just "/", return the root
        if len(segments) == 1 and segments[0] == "/":
            return current
        # Remove the leading '/' from segments for absolute paths
        segments = segments[1:]
    else:
        current = node

    for i, segment in enumerate(segments):
        if segment == ".":
            continue
        elif segment == "..":
            if current.parent is None:
                # Trying to go above root
                raise NodeNotFoundError(f"Path '{path}' resolves above root")
            current = current.parent
        else:
            if segment not in current._children:
                # Construct the partial path that failed
                failed_path_str = str(path.root / path.joinpath(*segments[:i+1])) if path.is_absolute() else str(path.joinpath(*segments[:i+1]))
                raise NodeNotFoundError(f"'{failed_path_str}' not found")
            current = current._children[segment]

    return current


def remove(node: Node, path: str | NodePath) -> Node:
    # Resolve the path to find the node to remove
    target_node = resolve(node, path)

    # TN-B2: refuse to remove the root
    if target_node.parent is None:
        raise InvalidTreeError("Cannot remove the root node")

    # Get the parent and name to detach
    parent = target_node.parent
    name = target_node.name

    # Detach the node and its subtree
    # We need to import detach from structure.py
    from branching_tree.structure import detach
    detached_node = detach(parent, name) # type: ignore

    return detached_node


def absolute_path(node: Node) -> NodePath:
    # TN-B3: path returns an absolute path
    path_segments = []
    current = node
    while current.parent is not None:
        path_segments.append(current.name)
        current = current.parent
    # The root node's name is None, so we need to handle it.
    # The absolute path should always start with '/', even for the root itself.
    if not path_segments: # This is the root node
        return NodePath("/")
    
    path_segments.reverse()
    return NodePath("/" + "/".join(path_segments))


def relative_path(node: Node, target: Node) -> NodePath:
    # TN-B3: Separate trees raise NotInSameTreeError
    # First, check if they are in the same tree by trying to resolve one from the other.
    # If resolve fails with NodeNotFoundError, they might be in different trees.
    # A more robust check is to find their common ancestor.

    # Get paths to check for shared root
    try:
        # This call to node.path and target.path will now work as absolute_path is implemented.
        node_path_str = str(node.path)
        target_path_str = str(target.path)
    except NotImplementedError: # This fallback is less likely to be needed now, but kept for robustness.
        # Fallback: Traverse up to find roots and compare.
        node_root = node
        while node_root.parent:
            node_root = node_root.parent
        target_root = target
        while target_root.parent:
            target_root = target_root.parent
        if node_root is not target_root:
            raise NotInSameTreeError("Nodes are not in the same tree")

    if node is target:
        return NodePath(".")

    # Find LCA (Lowest Common Ancestor)
    # The ancestors property is assumed to be implemented correctly.
    node_ancestors_set = set(node.ancestors)
    node_ancestors_set.add(node) # Include the node itself for LCA check

    current_target = target
    while current_target:
        if current_target in node_ancestors_set:
            lca = current_target
            break
        current_target = current_target.parent
    else:
        # This case should ideally not happen if the same tree check passed,
        # but as a safeguard:
        raise NotInSameTreeError("Could not find a common ancestor")

    # Construct path from node to LCA
    steps_up = []
    current = node
    while current is not None and current is not lca:
        steps_up.append("..")
        current = current.parent
        if current is None: # Should not happen if LCA logic is correct
            raise RuntimeError("Path construction error: node is not a descendant of LCA")

    # Construct path from LCA to target
    segments_down = []
    current = target
    while current is not None and current is not lca:
        segments_down.append(current.name)
        current = current.parent
        if current is None: # Should not happen if LCA logic is correct
            raise RuntimeError("Path construction error: target is not a descendant of LCA")
    segments_down.reverse() # Path from LCA down to target

    # Combine steps up and segments down
    relative_path_str = "/".join(steps_up + segments_down)
    return NodePath(relative_path_str)


def ancestors(node: Node) -> tuple[Node, ...]:
    """Return a tuple of all ancestor nodes, from the immediate parent up to the root."""
    ancestors_list = []
    current = node.parent
    while current is not None:
        ancestors_list.append(current)
        current = current.parent
    return tuple(ancestors_list)


def descendants(node: Node) -> tuple[Node, ...]:
    """Return a tuple of all descendant nodes in a depth-first, pre-order traversal."""
    descendant_nodes = []
    
    def dfs(current_node: Node):
        for child_name, child_node in current_node.children.items():
            descendant_nodes.append(child_node)
            dfs(child_node)

    dfs(node)
    return tuple(descendant_nodes)


def siblings(node: Node) -> tuple[Node, ...]:
    """Return a tuple of the node's siblings, maintaining insertion order."""
    if node.parent is None:
        return ()  # Root node has no siblings

    # Get all children of the parent and filter out the current node
    parent_children = list(node.parent.children.values())
    sibling_nodes = [sibling for sibling in parent_children if sibling is not node]
    return tuple(sibling_nodes)


def leaves(node: Node) -> tuple[Node, ...]:
    """Return a tuple of all leaf nodes in the subtree rooted at the current node."""
    leaf_nodes = []
    stack = [node]  # Start with the current node

    while stack:
        current = stack.pop()
        if not current.children:  # If the node has no children, it's a leaf
            leaf_nodes.append(current)
        else:
            # Add children in reverse order to process them in insertion order (left-to-right)
            # for a depth-first traversal.
            children_names = list(current.children.keys())
            for name in reversed(children_names):
                stack.append(current.children[name])
    return tuple(leaf_nodes)