from __future__ import annotations

from .model import Node, NodeNotFoundError, NodePath, NotInSameTreeError, InvalidTreeError


def resolve(node: Node, path: str | NodePath) -> Node:
    if not isinstance(path, NodePath):
        path = NodePath(path)

    current_node = node
    if path.is_absolute():
        # Find the root of the current node's tree
        while current_node.parent is not None:
            current_node = current_node.parent
        # If the path is absolute and doesn't start with '/', it's invalid
        if not path.is_absolute() or path.parts[0] != '/':
             raise NodeNotFoundError(f"Invalid absolute path: {path}")
        # Remove the leading '/' for iteration
        path_parts = path.parts[1:]
    else:
        path_parts = path.parts

    for part in path_parts:
        if part == ".":
            continue
        elif part == "..":
            if current_node.parent is None:
                raise NodeNotFoundError(f"Cannot move above root: {path}")
            current_node = current_node.parent
        else:
            if part not in current_node.children:
                raise NodeNotFoundError(f"Path segment '{part}' not found in {current_node.path}")
            current_node = current_node.children[part]

    return current_node


def remove(node: Node, path: str | NodePath) -> Node:
    resolved_node = resolve(node, path)

    if resolved_node.parent is None:
        raise InvalidTreeError("Cannot remove the root node.")

    return resolved_node.detach(resolved_node.name)


def absolute_path(node: Node) -> NodePath:
    if node.parent is None and node.name is None:
        return NodePath("/")

    path_parts = []
    current = node
    while current.parent is not None:
        path_parts.append(current.name)
        current = current.parent
    path_parts.reverse()
    return NodePath("/" + "/".join(path_parts))


def relative_path(node: Node, target: Node) -> NodePath:
    # Check if nodes are the same
    if node is target:
        return NodePath(".")

    # Find the root of the current node's tree
    root_node = node
    while root_node.parent is not None:
        root_node = root_node.parent

    # Find the root of the target node's tree
    target_root_node = target
    while target_root_node.parent is not None:
        target_root_node = target_root_node.parent

    # If the roots are different, they are in different trees
    if root_node is not target_root_node:
        raise NotInSameTreeError("Cannot compute relative path between nodes in different trees.")

    # Now we know they are in the same tree, proceed with path calculation
    start_path = absolute_path(node)
    target_path = absolute_path(target)

    common_len = 0
    for i in range(min(len(start_path.parts), len(target_path.parts))):
        if start_path.parts[i] == target_path.parts[i]:
            common_len += 1
        else:
            break

    # Number of '..' needed to go up from start_path to the common ancestor
    up_steps = len(start_path.parts) - common_len
    # Path from the common ancestor to the target
    down_parts = target_path.parts[common_len:]

    relative_parts = [".."] * up_steps + list(down_parts)

    # Handle the case where the target is the root and the current node is also the root
    # or if the relative path is empty (i.e., target is the current node, already handled)
    # or if the target is the parent and the current node is root.
    if not relative_parts and start_path == target_path:
        return NodePath(".")
    elif not relative_parts and target_path == NodePath("/"):
        # This means node is root, target is root. Already handled by node is target.
        # Or node is child of root, target is root.
        # E.g., node = a, target = root. start_path = "/a", target_path = "/"
        # common_len = 0. up_steps = 1. down_parts = []. relative_parts = [".."]
        # This case seems handled by the general logic.
        pass # Let the general logic handle it.

    return NodePath("/".join(relative_parts))


def ancestors(node: Node) -> tuple[Node, ...]:
    # Iterative approach:
    ancestors_list = []
    current = node.parent
    while current is not None:
        ancestors_list.append(current)
        current = current.parent
    return tuple(ancestors_list)


def descendants(node: Node) -> tuple[Node, ...]:
    # Performs a depth-first traversal to collect all descendants.
    result = []
    for child_name, child_node in node.children.items():
        result.append(child_node)
        result.extend(descendants(child_node))
    return tuple(result)


def siblings(node: Node) -> tuple[Node, ...]:
    # If the node has no parent, it has no siblings.
    if node.parent is None:
        return ()
    # Otherwise, return all children of the parent.
    # Get all children of the parent and filter out the node itself.
    # The children are already stored in insertion order in the dictionary.
    return tuple(child for child in node.parent.children.values() if child is not node)


def leaves(node: Node) -> tuple[Node, ...]:
    # If the node has no children, it is a leaf itself.
    if not node.children:
        return (node,)
    
    leaf_nodes = []
    # Recursively find leaves in all children.
    for child in node.children.values():
        leaf_nodes.extend(leaves(child))
    # Return the collected leaves as a tuple.
    return tuple(leaf_nodes)