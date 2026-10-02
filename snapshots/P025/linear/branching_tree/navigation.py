from __future__ import annotations

from .model import Node, NodePath, NodeNotFoundError, NotInSameTreeError


def resolve(node: Node, path: str | NodePath) -> Node:
    if not path:
        return node

    current_node = node
    path_obj = NodePath(path)

    if path_obj.is_absolute():
        # If the path is absolute, we need to start from the root.
        # This assumes the node passed in is part of a tree and has a root.
        # A more robust implementation might require a reference to the root.
        # For now, we'll traverse up to find the root.
        while current_node.parent is not None:
            current_node = current_node.parent
        
        # If the path starts with '/', remove it to match segment processing
        if path_obj.parts and path_obj.parts[0] == "":
            path_obj = NodePath(path_obj.parts[1:])

    for segment in path_obj.parts:
        if segment == ".":
            continue
        elif segment == "..":
            if current_node.parent is None:
                raise NodeNotFoundError("Cannot resolve '..' above the root")
            current_node = current_node.parent
        else:
            if segment not in current_node._children:
                raise NodeNotFoundError(f"Segment '{segment}' not found in path")
            current_node = current_node._children[segment]
    return current_node


def remove(node: Node, path: str | NodePath) -> Node:
    target_node = resolve(node, path)
    if target_node.parent is None:
        raise InvalidTreeError("Cannot remove the root node")

    # Detach the target node from its parent
    detached_node = target_node.parent.detach(target_node.name) # type: ignore
    return detached_node


def absolute_path(node: Node) -> NodePath:
    if node.parent is None:
        return NodePath("/")
    
    path_parts = []
    current = node
    while current.parent is not None:
        path_parts.append(current.name) # type: ignore
        current = current.parent
    
    path_parts.reverse()
    return NodePath("/" + "/".join(path_parts))


def relative_path(node: Node, target: Node) -> NodePath:
    node_path = node.path
    target_path = target.path

    if node_path.anchor != target_path.anchor:
        raise NotInSameTreeError("Cannot get relative path between nodes in different trees")

    common_len = 0
    for i in range(min(len(node_path.parts), len(target_path.parts))):
        if node_path.parts[i] == target_path.parts[i]:
            common_len += 1
        else:
            break

    # Number of steps up from the current node to the common ancestor
    up_steps = len(node_path.parts) - common_len
    # Path segments from the common ancestor to the target node
    down_parts = target_path.parts[common_len:]

    relative_parts = [".."] * up_steps + list(down_parts)
    return NodePath("/".join(relative_parts))


def ancestors(node: Node) -> tuple[Node, ...]:
    if node.parent is None:
        return ()
    
    all_ancestors = []
    current = node.parent
    while current is not None:
        all_ancestors.append(current)
        current = current.parent
    return tuple(all_ancestors)


def descendants(node: Node) -> tuple[Node, ...]:
    all_descendants = []
    
    def _traverse(current_node):
        for child in current_node.children.values():
            all_descendants.append(child)
            _traverse(child)
            
    _traverse(node)
    return tuple(all_descendants)


def siblings(node: Node) -> tuple[Node, ...]:
    if node.parent is None:
        return ()
    
    return tuple(
        child for child in node.parent.children.values() if child is not node
    )


def leaves(node: Node) -> tuple[Node, ...]:
    all_leaves = []

    def _traverse(current_node):
        if not current_node.children:
            all_leaves.append(current_node)
            return
        for child in current_node.children.values():
            _traverse(child)
            
    _traverse(node)
    return tuple(all_leaves)
