from __future__ import annotations

from .model import InvalidTreeError, Node, NodeNotFoundError, NodePath, NotInSameTreeError


def resolve(node: Node, path: str | NodePath) -> Node:
    if not path:
        return node

    current_node = node
    path_parts = NodePath(path).parts

    if path.startswith("/"):
        # Absolute path: start from the root
        while current_node.parent is not None:
            current_node = current_node.parent
        path_parts = path_parts[1:]  # Skip the leading '/'

    for part in path_parts:
        if part == ".":
            continue
        elif part == "..":
            if current_node.parent is None:
                raise NodeNotFoundError(f"Cannot move above the root node.")
            current_node = current_node.parent
        elif part in current_node.children:
            current_node = current_node.children[part]
        else:
            raise NodeNotFoundError(f"Segment '{part}' not found in path.")

    return current_node


def remove(node: Node, path: str | NodePath) -> Node:
    target_node = resolve(node, path)

    if target_node.parent is None:
        raise InvalidTreeError("Cannot remove the root node.")

    # Detach the target node from its parent
    detached_node = target_node.parent.detach(target_node.name)

    # Ensure the detached node's parent and name are cleared
    # (This should be handled by detach, but we assert for clarity and robustness)
    assert detached_node.parent is None
    assert detached_node.name is None

    return detached_node


def absolute_path(node: Node) -> NodePath:
    if node.parent is None:
        return NodePath("/")

    path_parts = []
    current = node
    while current.parent is not None:
        path_parts.append(current.name)
        current = current.parent
    path_parts.reverse()
    return NodePath("/" + "/".join(path_parts))


def relative_path(node: Node, target: Node) -> NodePath:
    node_path = absolute_path(node)
    target_path = absolute_path(target)

    if node_path.root != target_path.root:
        raise NotInSameTreeError("Cannot get relative path between nodes in different trees.")

    common_len = 0
    for i in range(min(len(node_path.parts), len(target_path.parts))):
        if node_path.parts[i] == target_path.parts[i]:
            common_len += 1
        else:
            break

    # Number of steps up from the current node to the common ancestor
    up_steps = len(node_path.parts) - common_len
    # Relative path parts
    relative_parts = [".."] * up_steps + list(target_path.parts[common_len:])

    return NodePath("/".join(relative_parts))


def ancestors(node: Node) -> tuple[Node, ...]:
    if node.parent is None:
        return ()

    current = node.parent
    ancestor_list = []
    while current is not None:
        ancestor_list.append(current)
        current = current.parent
    return tuple(ancestor_list)


def descendants(node: Node) -> tuple[Node, ...]:
    # This implements a depth-first, pre-order traversal.
    result = []
    nodes_to_visit = list(node.children.values())

    while nodes_to_visit:
        current_node = nodes_to_visit.pop(0)  # Get the first node (DFS style with queue)
        result.append(current_node)
        # Add children of the current node to the front of the list for pre-order
        nodes_to_visit = list(current_node.children.values()) + nodes_to_visit

    return tuple(result)


def siblings(node: Node) -> tuple[Node, ...]:
    raise NotImplementedError


def leaves(node: Node) -> tuple[Node, ...]:
    raise NotImplementedError
