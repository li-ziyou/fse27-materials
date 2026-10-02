from .model import Node, NodePath, InvalidTreeError, NodeNotFoundError, NotInSameTreeError
from .structure import detach  # This import is not used in the provided code snippet.


def resolve(node: Node, path: str | NodePath) -> Node:
    # TN-B1: Supports absolute and relative paths, including . and ..
    current = node
    path_obj = NodePath(path)

    if path_obj.is_absolute():
        # If the path is absolute, start from the root
        while current.parent:
            current = current.parent
        path_segments = list(path_obj.parts)
    else:
        # If the path is relative, start from the current node
        path_segments = list(path_obj.parts)

    for segment in path_segments:
        if segment == ".":
            continue
        elif segment == "..":
            if current.parent:
                current = current.parent
            else:
                # TN-B1: Movement above the root
                raise NodeNotFoundError("Cannot resolve path above root")
        else:
            if segment in current.children:
                current = current.children[segment]
            else:
                # TN-B1: Missing segments
                raise NodeNotFoundError(f"Path segment '{segment}' not found")
    return current


def remove(node: Node, path: str | NodePath) -> Node:
    # TN-B2: Refuses to remove the root
    if path == "/" or path == ".":
        raise InvalidTreeError("Cannot remove the root node")

    target_node = resolve(node, path)
    # TN-B2: Detaches the complete subtree
    return target_node.orphan()


def absolute_path(node: Node) -> NodePath:
    # TN-B3: Returns an absolute path
    if node.parent is None and node.name is None:
        # This node is orphaned, its path is effectively empty or undefined in a tree context
        return NodePath("/") # Assuming root of a tree is '/'

    parts = []
    current = node
    while current.parent:
        parts.append(current.name)
        current = current.parent
    parts.reverse()
    return NodePath("/" + "/".join(parts))


def relative_path(node: Node, target: Node) -> NodePath:
    # TN-B3: Returns a correct relative path for nodes in the same tree
    if node is target:
        return NodePath(".")

    node_parts = list(absolute_path(node).parts)
    target_parts = list(absolute_path(target).parts)

    # TN-B3: Separate trees raise NotInSameTreeError
    if not node_parts or not target_parts or node_parts[0] != target_parts[0]:
        raise NotInSameTreeError("Cannot find relative path between nodes in different trees")

    # Find the common ancestor
    common_len = 0
    while common_len < len(node_parts) and common_len < len(target_parts) and node_parts[common_len] == target_parts[common_len]:
        common_len += 1

    # Number of steps up from `node` to the common ancestor
    steps_up = len(node_parts) - common_len
    # Path segments from the common ancestor to `target`
    steps_down = target_parts[common_len:]

    relative_parts = [".."] * steps_up + steps_down
    return NodePath("/".join(relative_parts))


def ancestors(node: Node) -> tuple[Node, ...]:
    # TN-B4: Reflects the current tree and returns tuples
    if node.parent is None:
        return ()
    return (node.parent, *ancestors(node.parent))


def descendants(node: Node) -> tuple[Node, ...]:
    # TN-B4: Depth-first pre-order
    result = []
    for child_name, child_node in node.children.items():
        result.append(child_node)
        result.extend(descendants(child_node))
    return tuple(result)


def siblings(node: Node) -> tuple[Node, ...]:
    # TN-B4: Insertion-ordered
    if not node.parent:
        return ()
    return tuple(
        child for name, child in node.parent.children.items() if child is not node
    )


def leaves(node: Node) -> tuple[Node, ...]:
    # TN-B4: Depth-first
    if not node.children:
        return (node,)
    result = []
    for child_node in node.children.values():
        result.extend(leaves(child_node))
    return tuple(result)
