from __future__ import annotations

from .model import Node, NodePath, NodeNotFoundError, NotInSameTreeError

def _parse_path(path_str: str) -> list[str]:
    """Parses a path string into a list of segments, handling empty segments."""
    if not path_str:
        return []
    # Remove leading/trailing slashes and split, filter out empty strings from split
    return [segment for segment in path_str.strip("/").split("/") if segment]


def resolve(node: Node, path: str | NodePath) -> Node:
    current_node = node
    path_obj = NodePath(path) if isinstance(path, str) else path

    if path_obj.is_absolute():
        # If the path is absolute, we need to start from the root.
        # Traverse up to find the root.
        root = node
        while root.parent:
            root = root.parent
        current_node = root

    segments = _parse_path(str(path_obj))

    for segment in segments:
        if segment == ".":
            continue
        elif segment == "..":
            if current_node.parent is None:
                raise NodeNotFoundError("Cannot resolve '..' above the root.")
            current_node = current_node.parent
        elif segment in current_node.children:
            current_node = current_node.children[segment]
        else:
            raise NodeNotFoundError(f"Segment '{segment}' not found in path.")

    return current_node


def remove(node: Node, path: str | NodePath) -> Node:
    if node.path == NodePath(path):  # Attempting to remove the root itself
        raise InvalidTreeError("Cannot remove the root node.")

    target_node = resolve(node, path)
    if target_node.parent is None: # Should not happen if not root, but as a safeguard
        raise NodeNotFoundError("Target node not found (root cannot be removed).")

    return target_node.orphan()


def absolute_path(node: Node) -> NodePath:
    if node.parent is None:
        return NodePath("/")
    
    path_segments = []
    current = node
    while current.parent:
        if current.name is None:
            # This indicates an invalid state, should not happen in a valid tree
            raise InvalidTreeError("Node has a parent but no name.")
        path_segments.append(current.name)
        current = current.parent
    
    return NodePath("/" + "/".join(reversed(path_segments)))


def relative_path(node: Node, target: Node) -> NodePath:
    if node is target:
        return NodePath(".")

    node_ancestors = set(node.ancestors)
    target_ancestors = set(target.ancestors)

    if node.parent is None and target.parent is None and node is not target:
        raise NotInSameTreeError("Nodes are not in the same tree.")

    # Check if they share a common ancestor (which could be the root)
    common_ancestor = None
    node_path_to_common = []
    current_node = node
    while current_node:
        if current_node in target_ancestors:
            common_ancestor = current_node
            break
        node_path_to_common.append(current_node.name)
        current_node = current_node.parent
    
    if common_ancestor is None:
        # This case means they are in different trees, or one is an ancestor of the other
        # and the above loop didn't find it because it started from node.
        # If target is an ancestor of node, common_ancestor would be target.
        # If node is an ancestor of target, common_ancestor would be node.
        # The logic above should cover this. If still None, they are in different trees.
        raise NotInSameTreeError("Nodes are not in the same tree.")

    # Construct path from node up to common ancestor
    path_up = []
    current = node
    while current is not common_ancestor:
        if current.name is None:
            raise InvalidTreeError("Node in path has no name.")
        path_up.append(current.name)
        current = current.parent
        if current is None: # Should not happen if common_ancestor was found correctly
            raise InvalidTreeError("Error constructing path upwards.")

    # Construct path from common ancestor down to target
    path_down = []
    current = target
    while current is not common_ancestor:
        if current.name is None:
            raise InvalidTreeError("Node in path has no name.")
        path_down.append(current.name)
        current = current.parent
        if current is None: # Should not happen if common_ancestor was found correctly
            raise InvalidTreeError("Error constructing path downwards.")

    # Combine paths: '..' for each step up, then segments down
    relative_segments = [".."] * len(path_up) + list(reversed(path_down))

    return NodePath("/".join(relative_segments))


def ancestors(node: Node) -> tuple[Node, ...]:
    ancestor_list = []
    current = node.parent
    while current:
        ancestor_list.append(current)
        current = current.parent
    return tuple(ancestor_list)


def descendants(node: Node) -> tuple[Node, ...]:
    desc_list = []
    
    def _traverse(current_node: Node):
        for child in current_node.children.values():
            desc_list.append(child)
            _traverse(child)

    _traverse(node)
    return tuple(desc_list)


def siblings(node: Node) -> tuple[Node, ...]:
    if node.parent is None:
        return ()
    
    return tuple(
        child for name, child in node.parent.children.items() if child is not node
    )


def leaves(node: Node) -> tuple[Node, ...]:
    leaf_list = []

    def _traverse(current_node: Node):
        if not current_node.children:
            leaf_list.append(current_node)
            return
        for child in current_node.children.values():
            _traverse(child)
    
    _traverse(node)
    return tuple(leaf_list)
