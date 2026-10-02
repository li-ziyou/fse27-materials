from __future__ import annotations

from .model import Node, NodePath, NodeNotFoundError, NotInSameTreeError, InvalidTreeError
from .structure import detach


def _parse_path(path: str | NodePath) -> list[str]:
    if isinstance(path, NodePath):
        path = str(path)
    # Split by '/', filter out empty strings, and handle the root case.
    parts = [segment for segment in path.split("/") if segment]
    return parts


def resolve(node: Node, path: str | NodePath) -> Node:
    # First, ensure we are working with a NodePath object
    if isinstance(path, str):
        path_obj = NodePath(path)
    else:
        path_obj = path

    segments = _parse_path(path_obj) # Use _parse_path which handles NodePath correctly
    current = node

    if path_obj.is_absolute():
        # If the path is absolute, start from the root of the tree.
        # We need to find the root node first.
        root_node = node
        while root_node._parent is not None:
            root_node = root_node._parent
        current = root_node
        # Remove the leading '/' from the segments if it exists (handled by _parse_path)
        # segments = segments[1:] # This is implicitly handled by _parse_path
            
    for segment in segments:
        if segment == "..":
            if current._parent is None:
                raise NodeNotFoundError("Cannot resolve '..' above root.")
            current = current._parent
        elif segment == ".":
            pass  # Stay at the current node
        elif segment in current._children:
            current = current._children[segment]
        else:
            # Ensure 'current' is a Node object before accessing '.path'
            current_path = current.path if hasattr(current, 'path') else NodePath("/")
            raise NodeNotFoundError(f"Segment '{segment}' not found in '{current_path}'.")

    return current


def remove(node: Node, path: str | NodePath) -> Node:
    target_node = resolve(node, path)
    if target_node._parent is None and target_node._name is None: # If it's the root node
        raise InvalidTreeError("Cannot remove the root node.")
    
    if target_node._parent is None: # If it's an orphaned node, just return it
        return target_node

    return detach(target_node._parent, target_node._name)


def absolute_path(node: Node) -> NodePath:
    if node._parent is None:
        return NodePath("/")

    segments = []
    current = node
    while current._parent is not None:
        segments.append(current._name)
        current = current._parent
    return NodePath("/" + "/".join(reversed(segments)))


def relative_path(node: Node, target: Node) -> NodePath:
    if node is target:
        return NodePath(".")

    # Get absolute paths as lists of segments
    node_abs_path = node.path
    target_abs_path = target.path

    node_segments = [segment for segment in str(node_abs_path).split('/') if segment]
    target_segments = [segment for segment in str(target_abs_path).split('/') if segment]

    # Find the common ancestor length
    common_len = 0
    min_len = min(len(node_segments), len(target_segments))
    for i in range(min_len):
        if node_segments[i] == target_segments[i]:
            common_len += 1
        else:
            break

    # Calculate steps up and down
    up_steps = len(node_segments) - common_len
    down_segments = target_segments[common_len:]

    # Construct the relative path
    relative_parts = [".."] * up_steps + down_segments
    
    if not relative_parts:
        return NodePath(".")
        
    return NodePath("/".join(relative_parts))


def ancestors(node: Node) -> tuple[Node, ...]:
    if node._parent is None:
        return ()
    
    parent_chain = []
    current = node._parent
    while current is not None:
        parent_chain.append(current)
        current = current._parent
    return tuple(parent_chain)


def descendants(node: Node) -> tuple[Node, ...]:
    result = []
    stack = list(node._children.values())  # Start with direct children
    while stack:
        current_node = stack.pop(0)  # Get the first child in the list
        result.append(current_node)
        
        # Add its children to the front of the stack for pre-order traversal
        children_to_add = list(current_node._children.values())
        children_to_add.reverse() # Reverse to maintain insertion order when adding to front
        for child in children_to_add:
            stack.insert(0, child)
    return tuple(result)


def siblings(node: Node) -> tuple[Node, ...]:
    if node._parent is None:
        return ()
    
    return tuple(
        child for child in node._parent.children.values() if child is not node
    )


def leaves(node: Node) -> tuple[Node, ...]:
    if not node._children:
        return (node,)

    all_leaves = []
    for child in node._children.values():
        all_leaves.extend(leaves(child))
    return tuple(all_leaves)
