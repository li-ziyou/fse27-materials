from __future__ import annotations

from .model import InvalidTreeError, Node, NodeNotFoundError, NodePath, NotInSameTreeError
from .structure import detach

def resolve(node: Node, path: str | NodePath) -> Node:
    if not path:
        return node

    current = node
    path_obj = NodePath(path)

    if path_obj.is_absolute():
        current = node
        while current.parent is not None:
            current = current.parent
        path_segments = path_obj.parts[1:]  # Skip leading '/'
    else:
        path_segments = path_obj.parts

    for segment in path_segments:
        if segment == ".":
            continue
        elif segment == "..":
            if current.parent is None:
                raise NodeNotFoundError(f"Cannot resolve '..' from root: {path}")
            current = current.parent
        else:
            if segment not in current.children:
                raise NodeNotFoundError(f"Path segment '{segment}' not found in {current.path}: {path}")
            current = current.children[segment]
    return current


def remove(node: Node, path: str | NodePath) -> Node:
    target_node = resolve(node, path)
    if target_node.parent is None and target_node.name is None:  # It's the root
        raise NodeNotFoundError("Cannot remove the root node.")
    
    # Detach the node. The detach function in structure.py should handle clearing parent/name.
    # We need to resolve the parent first to call detach.
    parent_path = NodePath(path).parent
    parent_node = resolve(node, parent_path)
    detached_node = parent_node.detach(NodePath(path).name)
    return detached_node


def absolute_path(node: Node) -> NodePath:
    if node.parent is None:
        if node.name is None:
            raise InvalidTreeError("Node is detached and has no absolute path within a tree.")
        else:
            return NodePath("/")

    parts = []
    current = node
    while current.parent is not None:
        if current.name is None:
            raise InvalidTreeError("Node with parent has no name.")
        parts.append(current.name)
        current = current.parent
    
    return NodePath("/" + "/".join(reversed(parts)))


def relative_path(node: Node, target: Node) -> NodePath:
    if node is target:
        return NodePath(".")

    try:
        node_abs_path = absolute_path(node)
        target_abs_path = absolute_path(target)
    except InvalidTreeError:
        # If either node cannot have an absolute path determined, they are not in the same tree.
        raise NotInSameTreeError("Nodes are not in the same tree.")

    node_parts = node_abs_path.parts
    target_parts = target_abs_path.parts

    # Find the length of the common prefix
    common_len = 0
    for i in range(min(len(node_parts), len(target_parts))):
        if node_parts[i] == target_parts[i]:
            common_len += 1
        else:
            break

    # If the common prefix is empty and both are root, they are in the same tree (which is root)
    # If common_len is 1 and node_parts[0] is '/', target_parts[0] is '/', they are in the same tree.
    if node_parts[0] != target_parts[0]:
        # If the first segment (root indicator) is different, they are in different trees.
        raise NotInSameTreeError("Nodes are not in the same tree.")
    
    # If common_len is 1, it means the common part is just the root '/'.
    # If common_len is 0, it means no common root, hence different trees.
    # The following check for common_len == 0 is actually redundant because
    # node_parts[0] != target_parts[0] would have already caught it.


    # Number of steps up from 'node' to the common ancestor
    up_steps = len(node_parts) - common_len
    # Path segments from the common ancestor to 'target'
    down_segments = target_parts[common_len:]

    relative_parts = [".."] * up_steps + list(down_segments)
    
    # Handle the case where the target is an ancestor of the node
    if not relative_parts:
        return NodePath(".")
    
    # Filter out empty strings that might arise from joining segments like ".."
    return NodePath("/".join(relative_segments for relative_segments in relative_parts if relative_segments))


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
    all_descendants = []
    
    def traverse(current_node: Node):
        for child in current_node.children.values():
            all_descendants.append(child)
            traverse(child)

    traverse(node)
    return tuple(all_descendants)


def siblings(node: Node) -> tuple[Node, ...]:
    if node.parent is None:
        return ()
    
    return tuple(
        sibling for sibling in node.parent.children.values() if sibling is not node
    )


def leaves(node: Node) -> tuple[Node, ...]:
    leaf_nodes = []
    
    def traverse(current_node: Node):
        if not current_node.children:
            leaf_nodes.append(current_node)
        else:
            for child in current_node.children.values():
                traverse(child)

    traverse(node)
    return tuple(leaf_nodes)
