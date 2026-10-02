from __future__ import annotations

from .model import Node, NodePath, NodeNotFoundError, NotInSameTreeError


def resolve(node: Node, path: str | NodePath) -> Node:
    current = node
    if isinstance(path, str):
        path = NodePath(path)

    if path.is_absolute():
        # If the path is absolute, start resolution from the root of the tree
        while current.parent is not None:
            current = current.parent
        # Make the path relative to the root
        path = path.relative_to(current.path)

    # Iterate through each segment of the path
    for segment in path.parts:
        if segment == ".":
            # Current directory, do nothing
            continue
        elif segment == "..":
            if current.parent is None:
                raise NodeNotFoundError(f"Cannot resolve '{path}': movement above root")
            current = current.parent
        elif segment in current.children:
                current = current.children[segment]
        else:
            raise NodeNotFoundError(f"Cannot resolve '{path}': segment '{segment}' not found")
    return current


def remove(node: Node, path: str | NodePath) -> Node:
    """
    Resolves a path and detaches the node at that path.

    - Refuses to remove the root node.
    - Returns the detached node.
    """
    # Resolve the target node using the provided path
    target = resolve(node, path)
    
    # TN-B2: Refuse to remove the root node
    if target.parent is None:
        raise InvalidTreeError("Cannot remove the root node")
    
    # Detach the target node from its parent. The detach method handles clearing
    # the parent and name attributes of the detached node.
    # We need to use the name of the target node when calling detach on its parent.
    if target.name is None:
        raise NodeNotFoundError(f"Cannot remove node at path '{path}': target node has no name")
    return target.parent.detach(target.name)


def absolute_path(node: Node) -> NodePath:
    if node.parent is None:
        return NodePath("/")
    # Ensure node.name is not None before joining
    if node.name is None:
        raise InvalidTreeError("Node has no name, cannot determine path")
    return node.parent.path / node.name


def relative_path(node: Node, target: Node) -> NodePath:
    # Handle cases where node or target might be the root or detached
    if node is target:
        return NodePath(".")

    node_path = node.path
    target_path = target.path

    # TN-B3: Handle cases where nodes might be detached or not in the same tree.
    # A detached node has no parent and thus no path.
    if node.parent is None or target.parent is None:
        raise NotInSameTreeError("Cannot determine relative path to/from detached node")
        
    node_path = node.path
    target_path = target.path

    # If paths are not in the same tree (e.g., different roots)
    if node_path.root != target_path.root:
        raise NotInSameTreeError("Nodes are not in the same tree")

    # Find the common ancestor path by comparing parts
    common_parts = []
    # Iterate through the parts of both paths to find the common prefix
    min_len = min(len(node_path.parts), len(target_path.parts))
    for i in range(min_len):
        if node_path.parts[i] == target_path.parts[i]:
            common_parts.append(node_path.parts[i])
        else:
            break

    # Number of steps up from node to common ancestor
    steps_up = len(node_path.parts) - len(common_parts)

    # Segments from common ancestor to target
    steps_down = target_path.parts[len(common_parts):]

    # Construct the relative path
    path_segments = [".."] * steps_up + list(steps_down)

    # TN-B3: Ensure that if the path is empty (e.g., same node), it's represented as "."
    if not path_segments:
        return NodePath(".")

    return NodePath(*path_segments)


def ancestors(node: Node) -> tuple[Node, ...]:
    result = []
    current = node.parent
    while current is not None:
        result.append(current)
        current = current.parent
    return tuple(result)


def descendants(node: Node) -> tuple[Node, ...]:
    result = []
    # Use a list as a queue for breadth-first traversal, or a stack for depth-first.
    # For pre-order traversal, we process the node first, then its children.
    # We'll use a list as a stack for depth-first traversal.
    
    # Start with the children of the current node
    nodes_to_visit = list(node.children.values())
    
    while nodes_to_visit:
        current_node = nodes_to_visit.pop(0) # Use pop(0) for queue (BFS), pop() for stack (DFS)
        result.append(current_node)
        
        # Add children to the *front* of the list to maintain DFS order
        # and process them in insertion order if possible.
        # Python dicts maintain insertion order since 3.7.
        # We iterate in reverse to ensure correct order when popping from the front.
        for child_name, child_node in reversed(list(current_node.children.items())):
            nodes_to_visit.insert(0, child_node)
            
    return tuple(result)


def siblings(node: Node) -> tuple[Node, ...]:
    if node.parent is None:
        # A root node has no siblings
        return ()
    return tuple(
        sibling for name, sibling in node.parent.children.items() if sibling is not node
    )


def leaves(node: Node) -> tuple[Node, ...]:
    result = []
    nodes_to_visit = list(node.children.values())
    while nodes_to_visit:
        current = nodes_to_visit.pop(0)
        if not current.children:
            result.append(current)
        else:
            nodes_to_visit.extend(current.children.values())
    return tuple(result)
