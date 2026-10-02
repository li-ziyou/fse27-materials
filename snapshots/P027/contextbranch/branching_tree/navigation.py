from __future__ import annotations

from .model import Node, NodePath, NodeNotFoundError, NotInSameTreeError, InvalidTreeError


def resolve(node: Node, path: str | NodePath) -> Node:
    """Resolve a path relative to the given node."""
    if isinstance(path, str):
        path = NodePath(path)

    current_node = node
    if path.is_absolute():
        # If the path is absolute, we need to find the root first.
        # This assumes that the root's parent is None.
        while current_node.parent is not None:
            current_node = current_node.parent
        # Now current_node is the root.
        # Skip the root part of the path if it's absolute.
        # The first part of an absolute path is always '/', which we can skip.
        path_parts = path.parts[1:] if path.is_absolute() and path.parts else path.parts
    else:
        path_parts = path.parts

    for part in path_parts:
        if part == ".":
            continue
        elif part == "..":
            if current_node.parent is None:
                raise NodeNotFoundError(f"Cannot navigate above the root with path: {path}")
            current_node = current_node.parent
        else:
            # If the part is '/', it means the path is malformed or we are trying to access the root itself in an invalid way.
            # For example, resolving '/' from a non-root node.
            if part == '/':
                raise NodeNotFoundError(f"Invalid path segment '/' encountered in path: {path}")
            try:
                current_node = current_node.children[part]
            except KeyError:
                raise NodeNotFoundError(f"Path segment '{part}' not found in path: {path}")
    return current_node


def remove(node: Node, path: str | NodePath) -> Node:
    """Remove a node at the given path and return it."""
    if isinstance(path, str):
        path = NodePath(path)
        
    resolved_node = resolve(node, path)

    # Check if the resolved node is the root of the tree from which 'node' originates
    # If 'node' is the root, then resolved_node must also be the root to be disallowed.
    # If 'node' is not the root, and resolved_node is the root of *its* tree, it's a different tree.
    # The check for NotInSameTreeError in relative_path and the logic in resolve should handle cross-tree scenarios.
    # The primary concern here is removing the root of the *current* tree.
    if resolved_node.parent is None:
        # If the node to be removed is the root, and the original node is also the root, then it's disallowed.
        if node.parent is None and resolved_node is node:
            raise InvalidTreeError("Cannot remove the root node.")
        # If the node to be removed is the root of *another* tree, and 'node' is not that root,
        # it implies a cross-tree operation that should have been caught earlier or is not intended.
        # For now, we'll assume that if resolved_node.parent is None, and it's not the 'node' itself,
        # it's an edge case that might be handled by other checks or is a separate tree.
        # The most direct check is if resolved_node is *the* root of the tree we are operating on.
        if node.path.root == resolved_node.path.root and resolved_node.parent is None:
             raise InvalidTreeError("Cannot remove the root node.")


    if resolved_node.parent:
        # Detach the resolved node from its parent
        parent = resolved_node.parent
        if resolved_node.name: # Should always have a name if it has a parent
            # Directly modify the internal _children dictionary, not the read-only children view.
            del parent._children[resolved_node.name]
        
        resolved_node._parent = None
        resolved_node._name = None
    else:
        # This case should be caught by the root check above. If we reach here, it's an unexpected state.
        raise InvalidTreeError("Cannot remove a node without a parent, which should be the root.")
        
    return resolved_node


def absolute_path(node: Node) -> NodePath:
    """Return the absolute path of the node."""
    if node.parent is None:
        return NodePath("/")
    
    path_parts = []
    current = node
    while current.parent is not None:
        if current.name is None: # Should not happen for nodes with parents
            raise InvalidTreeError("Node with parent has no name.")
        path_parts.append(current.name)
        current = current.parent
    
    return NodePath("/" + "/".join(reversed(path_parts)))


def relative_path(node: Node, target: Node) -> NodePath:
    """Return the relative path from node to target."""
    node_abs_path = absolute_path(node)
    target_abs_path = absolute_path(target)

    # Check if they are in the same tree by comparing their root nodes.
    # This is a more robust check than just comparing paths.
    node_root = node.parent is None and node or absolute_path(node).root
    target_root = target.parent is None and target or absolute_path(target).root

    if node_root is not target_root:
        raise NotInSameTreeError("Cannot determine relative path between nodes in different trees.")

    if node is target:
        return NodePath(".")


    node_parts = list(node_abs_path.parts)
    target_parts = list(target_abs_path.parts)

    # Find the common ancestor
    common_len = 0
    while common_len < len(node_parts) and common_len < len(target_parts) and node_parts[common_len] == target_parts[common_len]:
        common_len += 1

    # Number of steps up from node to common ancestor
    steps_up = len(node_parts) - common_len
    
    # Path from common ancestor to target
    relative_parts = target_parts[common_len:]

    # Construct the relative path
    path_segments = [".."] * steps_up + relative_parts
    
    # If the resulting path is empty, it means node and target are the same.
    if not path_segments:
        return NodePath(".")
    
    return NodePath("/".join(path_segments))


def ancestors(node: Node) -> tuple[Node, ...]:
    """Return all ancestors of the node."""
    ancestors_list = []
    current = node.parent
    while current is not None:
        ancestors_list.append(current)
        current = current.parent
    return tuple(ancestors_list)


def descendants(node: Node) -> tuple[Node, ...]:
    """Return all descendants in depth-first, pre-order."""
    desc_list = []
    # Use a list as a stack for DFS. For pre-order, we process the node first,
    # then add its children to the stack in reverse order so they are popped in the correct order.
    stack = list(node.children.values())
    # Reverse the initial children so that the first child is processed first when popping from the stack.
    stack.reverse()

    while stack:
        current = stack.pop() # Get the next node to process
        desc_list.append(current)

        # Add the children of the current node to the stack.
        # Add them in reverse order so that the first child is at the top of the stack.
        children_to_add = list(current.children.values())
        children_to_add.reverse()
        stack.extend(children_to_add)

    return tuple(desc_list)


def siblings(node: Node) -> tuple[Node, ...]:
    """Return siblings of the node in insertion order."""
    if node.parent is None:
        return ()
    # The children dictionary is insertion ordered in Python 3.7+
    return tuple(sibling for sibling in node.parent.children.values() if sibling is not node)


def leaves(node: Node) -> tuple[Node, ...]:
    """Return all leaf nodes in the subtree rooted at node."""
    leaf_list = []
    # Use a stack for DFS.
    stack = list(node.children.values())
    # Reverse the initial children so that the first child is processed first when popping from the stack.
    stack.reverse()

    while stack:
        current = stack.pop() # Get the next node to process
        if not current.children:
            leaf_list.append(current)
        else:
            # Add children to the stack in reverse order to maintain insertion order.
            children_to_add = list(current.children.values())
            children_to_add.reverse()
            stack.extend(children_to_add)

    return tuple(leaf_list)
