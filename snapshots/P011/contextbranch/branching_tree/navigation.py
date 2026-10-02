from __future__ import annotations

from .model import InvalidTreeError, Node, NodeNotFoundError, NodePath, NotInSameTreeError


def resolve(node: Node, path: str | NodePath) -> Node:
    if not path:
        return node

    target_path = NodePath(path) if isinstance(path, str) else path

    if target_path.is_absolute():
        # If the path is absolute, start from the root of the tree.
        current = node
        while current.parent is not None:
            current = current.parent
        
        # Skip the first segment if it's empty (representing the root "/")
        segments_to_resolve = list(target_path.parts)
        if segments_to_resolve and segments_to_resolve[0] == "":
            segments_to_resolve = segments_to_resolve[1:]
    else:
        # If the path is relative, start from the current node.
        current = node
        segments_to_resolve = target_path.parts

    for segment in segments_to_resolve:
        if segment == "." or segment == "":
            # Ignore current directory and empty segments.
            continue
        elif segment == "..":
            # Move up to the parent directory.
            if current.parent is None:
                raise NodeNotFoundError(f"Cannot resolve path '{path}' (moving above root)")
            current = current.parent
        elif segment in current.children:
            # Move to the child node.
            current = current.children[segment]
        else:
            raise NodeNotFoundError(f"Cannot resolve path '{path}': segment '{segment}' not found.")
    return current


def remove(node: Node, path: str | NodePath) -> Node:
    target_node = resolve(node, path)
    if target_node.parent is None:
        raise InvalidTreeError("Cannot remove the root node.")
    return target_node.detach(target_node.name)


def absolute_path(node: Node) -> NodePath:
    if node.parent is None:
        return NodePath("/")
    
    path_parts = []
    current = node
    while current.parent is not None:
        path_parts.append(current.name)
        current = current.parent
    
    return NodePath("/" + "/".join(reversed(path_parts)))


def relative_path(node: Node, target: Node) -> NodePath:
    if node is target:
        return NodePath(".")

    # If target node is not attached to any tree, it cannot be in the same tree.
    if target.parent is None and target.name is None and target.path.root == "/":
        raise NotInSameTreeError("Cannot determine relative path to a detached node.")

    node_abs_path = node.path
    target_abs_path = target.path

    if node_abs_path.root != target_abs_path.root:
         raise NotInSameTreeError("Cannot determine relative path between nodes in different trees.")

    node_path_parts = node_abs_path.parts
    target_path_parts = target_abs_path.parts

    # Find the common ancestor
    common_len = 0
    while common_len < len(node_path_parts) and common_len < len(target_path_parts) and node_path_parts[common_len] == target_path_parts[common_len]:
        common_len += 1

    # Number of steps up from node to common ancestor
    up_steps = len(node_path_parts) - common_len
    
    # Segments from common ancestor to target
    down_segments = target_path_parts[common_len:]

    relative_parts = [".."] * up_steps + list(down_segments)
    
    if not relative_parts:
        return NodePath(".")
    
    return NodePath("/".join(relative_parts))


def ancestors(node: Node) -> tuple[Node, ...]:
    if node.parent is None:
        return ()
    return (*node.parent.ancestors, node.parent)


def descendants(node: Node) -> tuple[Node, ...]:
    nodes = []
    for child in node.children.values():
        nodes.append(child)
        nodes.extend(child.descendants)
    return tuple(nodes)


def siblings(node: Node) -> tuple[Node, ...]:
    if node.parent is None:
        return ()
    return tuple(
        child for name, child in node.parent.children.items() if child is not node
    )


def leaves(node: Node) -> tuple[Node, ...]:
    if not node.children:
        return (node,)
    
    nodes = []
    for child in node.children.values():
        nodes.extend(child.leaves)
    return tuple(nodes)
