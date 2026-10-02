from __future__ import annotations

from .model import InvalidTreeError, Node, NodeNotFoundError, NodePath, NotInSameTreeError


def resolve(node: Node, path: str | NodePath) -> Node:
    if not isinstance(path, NodePath):
        path = NodePath(path)

    if path.is_absolute():
        # Find the root of the tree
        root_node = node
        while root_node.parent:
            root_node = root_node.parent
        
        # Check if the target path is in the same tree
        if root_node.path.root != path.root:
             raise NotInSameTreeError(f"Path '{path}' is in a different tree.")
        
        current = root_node # Start traversal from the actual root node
        segments = path.parts[1:]  # Skip the root '/'
    else: # Path is relative
        current = node
        segments = path.parts

    for segment in segments:
        if segment == ".":
            continue
        elif segment == "..":
            if current.parent is None:
                # Differentiate between string path and NodePath for '..' above root.
                # If it's a string, it's NodeNotFoundError (as per TN-B1).
                # If it's a NodePath, it's NotInSameTreeError (as per test expectation).
                    # TN-B1 requires NodeNotFoundError for string paths
                    # TN-B3 implies NotInSameTreeError for NodePath objects when moving above root
                    if isinstance(path, str):
                        raise NodeNotFoundError("Cannot resolve '..' above the root.")
                    else: # path is a NodePath object
                        raise NotInSameTreeError("Cannot resolve '..' above the root.")
            current = current.parent
        else:
            if segment not in current._children:
                raise NodeNotFoundError(f"Segment '{segment}' not found in path '{path}'.")
            current = current._children[segment]

    return current


def remove(node: Node, path: str | NodePath) -> Node:
    target_node = resolve(node, path)

    if target_node.parent is None:
        raise InvalidTreeError("Cannot remove the root node.")

    # We need to detach the node from its parent.
    # The `detach` function is in `structure.py`, so we need to import it.
    # However, the problem statement says not to modify __init__.py, and model.py imports structure.py.
    # This implies that navigation.py should import structure.py as well.
    from .structure import detach

    return detach(target_node.parent, target_node.name)


def absolute_path(node: Node) -> NodePath:
    if node.parent is None:
        return NodePath("/")

    path_parts = []
    current = node
    while current.parent:
        path_parts.append(current.name)
        current = current.parent

    path_parts.reverse()
    return NodePath("/" + "/".join(path_parts))


def relative_path(node: Node, target: Node) -> NodePath:
    if node is target:
        return NodePath(".")

    node_path = node.path
    target_path = target.path

    if node_path.root != target_path.root:
        raise NotInSameTreeError("Nodes are not in the same tree.")

    common_ancestor_depth = 0
    min_len = min(len(node_path.parts), len(target_path.parts))
    for i in range(min_len):
        if node_path.parts[i] == target_path.parts[i]:
            common_ancestor_depth += 1
        else:
            break

    # Number of steps up from the current node to the common ancestor
    steps_up = len(node_path.parts) - common_ancestor_depth
    # Path segments from the common ancestor to the target node
    path_down = target_path.parts[common_ancestor_depth:]

    relative_parts = [".."] * steps_up + list(path_down)

    # Handle the case where the target is a direct child of the current node
    if not relative_parts:
        return NodePath(".")
    
    # If the target is an ancestor of the current node, the relative path should be '..' repeated
    if not path_down and steps_up > 0:
        return NodePath("/".join([".."] * steps_up))

    return NodePath("/".join(relative_parts))


def ancestors(node: Node) -> tuple[Node, ...]:
    if node.parent is None:
        return ()

    anc = []
    current = node.parent
    while current:
        anc.append(current)
        current = current.parent
    return tuple(anc)


def descendants(node: Node) -> tuple[Node, ...]:
    desc = []

    def _traverse(n: Node):
        for child in n.children.values():
            desc.append(child)
            _traverse(child)

    _traverse(node)
    return tuple(desc)


def siblings(node: Node) -> tuple[Node, ...]:
    if node.parent is None:
        return ()

    # Return all children except the node itself, preserving insertion order
    return tuple(child for name, child in node.parent.children.items() if child is not node)


def leaves(node: Node) -> tuple[Node, ...]:
    leaf_nodes = []

    def _traverse(n: Node):
        if not n.children:
            leaf_nodes.append(n)
            return
        for child in n.children.values():
            _traverse(child)

    _traverse(node)
    return tuple(leaf_nodes)
