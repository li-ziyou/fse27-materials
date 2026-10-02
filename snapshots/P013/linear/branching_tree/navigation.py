from __future__ import annotations

from .model import Node, NodePath, NodeNotFoundError, NotInSameTreeError


def resolve(node: Node, path: str | NodePath) -> Node:
    if not isinstance(path, NodePath):
        path = NodePath(path)

    current_node = node
    if path.is_absolute():
        # If the path is absolute, we need to find the root first.
        # This assumes the root has no parent.
        while current_node.parent is not None:
            current_node = current_node.parent
        target_path = path.relative_to(current_node.path) # Get path relative to root
    else:
        target_path = path

    # Traverse the path
    for segment in target_path.parts:
        if segment == "." or segment == "":
            continue
        elif segment == "..":
            if current_node.parent is None:
                raise NodeNotFoundError("Cannot go above the root")
            current_node = current_node.parent
        else:
            if segment not in current_node.children:
                raise NodeNotFoundError(f"Segment '{segment}' not found in path")
            current_node = current_node.children[segment]

    return current_node


def remove(node: Node, path: str | NodePath) -> Node:
    if not isinstance(path, NodePath):
        path = NodePath(path)

    # TN-B2: refuse to remove the root
    if path == "." or path == "/" or path == "":
        raise InvalidTreeError("Cannot remove the root node")

    target_node = resolve(node, path)

    # If the target node is the root, we cannot remove it.
    if target_node.parent is None and target_node.name is None:
        raise InvalidTreeError("Cannot remove the root node")

    # Detach the subtree
    return target_node.orphan()


def absolute_path(node: Node) -> NodePath:
    if node.parent is None and node.name is None:
        # This is the root node
        return NodePath("/")

    path_segments = []
    current = node
    while current.parent is not None:
        path_segments.append(current.name)
        current = current.parent
    
    # The root's path is "/", so we reverse and join.
    # If node is root, path_segments will be empty, so we return "/"
    if not path_segments:
        return NodePath("/")
    
    return NodePath("/" + "/".join(reversed(path_segments)))


def relative_path(node: Node, target: Node) -> NodePath:
    # TN-B3: `relative_path_to` returns a correct relative path for nodes in the same tree; separate trees raise `NotInSameTreeError`.
    
    # Ensure both nodes are valid and have paths.
    if not hasattr(node, 'path') or not hasattr(target, 'path'):
        raise ValueError("Both nodes must have a valid path attribute.")

    def get_root_node(n: Node) -> Node:
        """Helper function to find the ultimate root node of a given node."""
        current = n
        while current.parent is not None:
            current = current.parent
        return current

    root_node_of_node = get_root_node(node)
    root_node_of_target = get_root_node(target)

    # TN-B3: separate trees raise `NotInSameTreeError`.
    if root_node_of_node is not root_node_of_target:
        raise NotInSameTreeError("Cannot get relative path between nodes in different trees")

    # Now we know they are in the same tree, so we can safely use their paths.
    node_abs_path = node.path
    target_abs_path = target.path

    node_path_parts = node_abs_path.parts
    target_path_parts = target_abs_path.parts

    # Find the common ancestor by comparing path segments
    common_len = 0
    min_len = min(len(node_path_parts), len(target_path_parts))
    for i in range(min_len):
        if node_path_parts[i] == target_path_parts[i]:
            common_len += 1
        else:
            break

    # Number of '..' needed to go up from the current node to the common ancestor
    up_levels = len(node_path_parts) - common_len
    # Segments from the common ancestor to the target node
    down_segments = target_path_parts[common_len:]

    # Construct the relative path
    relative_segments = [".."] * up_levels + list(down_segments)

    # If relative_segments is empty, it means node and target are the same.
    # In this case, the relative path is "."
    if not relative_segments:
        return NodePath(".")
    
    # NodePath constructor handles joining segments correctly.
    return NodePath("/".join(relative_segments))


def ancestors(node: Node) -> tuple[Node, ...]:
    # TN-B4: `ancestors` reflect the current tree and return tuples.
    if node.parent is None and node.name is None:
        # Root node has no ancestors
        return ()

    ancestor_list = []
    current = node.parent
    while current is not None:
        ancestor_list.append(current)
        current = current.parent
    return tuple(ancestor_list)


def descendants(node: Node) -> tuple[Node, ...]:
    # TN-B4: depth-first pre-order `descendants` reflect the current tree and return tuples.
    all_descendants = []
    
    def _traverse(current_node: Node):
        # We want to exclude the node itself from its descendants
        for child_name, child_node in current_node.children.items():
            all_descendants.append(child_node)
            _traverse(child_node)

    _traverse(node)
    return tuple(all_descendants)


def siblings(node: Node) -> tuple[Node, ...]:
    # TN-B4: insertion-ordered `siblings` reflect the current tree and return tuples.
    if node.parent is None:
        # Root node has no siblings
        return ()

    # Get all children from the parent and filter out the current node
    return tuple(
        child for name, child in node.parent.children.items() if child is not node
    )


def leaves(node: Node) -> tuple[Node, ...]:
    # TN-B4: depth-first `leaves` reflect the current tree and return tuples.
    all_leaves = []

    def _traverse(current_node: Node):
        if not current_node.children:
            # This is a leaf node
            all_leaves.append(current_node)
            return
        
        # Recurse on children
        for child_name, child_node in current_node.children.items():
            _traverse(child_node)

    _traverse(node)
    return tuple(all_leaves)
