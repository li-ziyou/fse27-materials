from __future__ import annotations

from .model import Node, NodeNotFoundError, NodePath, NotInSameTreeError


def resolve(node: Node, path: str | NodePath) -> Node:
    if not isinstance(path, NodePath):
        path = NodePath(path)

    if path.is_absolute():
        current = node  # Start from the root if the path is absolute
        segments = path.parts[1:]  # Skip the leading '/'
    else:
        current = node
        segments = path.parts

    for segment in segments:
        if segment == ".":
            continue
        elif segment == "..":
            if current.parent is None:
                raise NodeNotFoundError(f"Cannot move above the root: {path}")
            current = current.parent
        elif segment in current.children:
            current = current.children[segment]
        else:
            raise NodeNotFoundError(f"Path segment not found: {segment} in {path}")

    return current


def remove(node: Node, path: str | NodePath) -> Node:
    target_node = resolve(node, path)

    if target_node.parent is None and target_node.name is None:
        raise NodeNotFoundError("Cannot remove the root node.")

    if target_node.parent:
        detached_node = target_node.parent.detach(target_node.name)
        return detached_node
    else:
        # This case should ideally not be reached if the root check is effective,
        # but as a safeguard, if a node somehow has no parent but isn't the root,
        # we'll orphan it.
        return target_node.orphan()


def absolute_path(node: Node) -> NodePath:
    if node.parent is None:
        return NodePath("/")
    
    path_parts = []
    current = node
    while current.parent is not None:
        if current.name is None: # Should not happen for non-root nodes
            raise InvalidTreeError("Node has no name but has a parent.")
        path_parts.append(current.name)
        current = current.parent
    
    return NodePath("/" + "/".join(reversed(path_parts)))


def relative_path(node: Node, target: Node) -> NodePath:
    if node is target:
        return NodePath(".")

    node_path = node.path
    target_path = target.path

    # If target node has no parent and the current node is not the root,
    # they are likely in different trees.
    # Also, if node.path.root and target.path.root are different, they are in different trees.
    # Note: node_path.root is just '/', so this check is for absolute paths.
    
    # Check for detached nodes: a node with no parent and no name is not in any tree.
    is_node_detached = node.parent is None and node.name is None
    is_target_detached = target.parent is None and target.name is None

    if is_node_detached or is_target_detached:
        raise NotInSameTreeError("Cannot get relative path involving a detached node.")

    if node_path.root != target_path.root:
        raise NotInSameTreeError("Cannot get relative path between nodes in different trees.")

    common_len = 0
    for i in range(min(len(node_path.parts), len(target_path.parts))):
        if node_path.parts[i] == target_path.parts[i]:
            common_len += 1
        else:
            break

    # Number of steps up from node to the common ancestor
    up_steps = len(node_path.parts) - common_len
    # Segments from the common ancestor to the target
    down_segments = target_path.parts[common_len:]

    relative_parts = [".."] * up_steps + list(down_segments)
    
    # Check if the target is an ancestor of the node.
    # This occurs when the node_path is a descendant of target_path.
    # If node_path is a descendant of target_path, then relative_parts will be empty
    # after calculating up_steps and down_segments.
    is_target_ancestor = len(node_path.parts) > len(target_path.parts) and \
                         node_path.parts[:len(target_path.parts)] == target_path.parts

    if not relative_parts and is_target_ancestor:
        return NodePath(".")
        
    return NodePath("/".join(relative_parts))


def ancestors(node: Node) -> tuple[Node, ...]:
    if node.parent is None:
        return ()
    
    ancestors_list = []
    current = node.parent
    while current is not None:
        ancestors_list.append(current)
        current = current.parent
    return tuple(ancestors_list)


def descendants(node: Node) -> tuple[Node, ...]:
    desc_list = []
    
    def _traverse(current_node: Node):
        for child_name, child_node in current_node.children.items():
            desc_list.append(child_node)
            _traverse(child_node)
            
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
        
        for child_name, child_node in current_node.children.items():
            _traverse(child_node)
            
    _traverse(node)
    return tuple(leaf_list)
