from __future__ import annotations

from .model import Node, NodePath, NodeNotFoundError, NotInSameTreeError


def _get_root(node: Node) -> Node:
    """Helper to find the root of the tree."""
    current = node
    while current.parent:
        current = current.parent
    return current


def resolve(node: Node, path: str | NodePath) -> Node:
    """
    Resolves a path relative to the given node.
    Supports absolute paths, relative paths, '.', and '..'.
    """
    if not isinstance(path, NodePath):
        path = NodePath(path)

    if path.is_absolute():
        current = _get_root(node)
    else:
        current = node

    # NodePath.parts includes the leading '/' for absolute paths, e.g., '/a/b' -> ('/', 'a', 'b')
    # We need to handle the root path '/' correctly.
    path_segments = list(path.parts)

    if path.is_absolute() and path_segments[0] == '/':
        current = _get_root(node)
        # If the path is just '/', we are already at the root.
        if len(path_segments) == 1:
            return current
        # Remove the root segment '/' to process actual child names
        path_segments = path_segments[1:]
    else:
        current = node

    for segment in path_segments:
        if segment == ".":
            continue
        elif segment == "..":
            if current.parent is None:
                raise NodeNotFoundError(f"Cannot resolve path above root: {path}")
            current = current.parent
        else:
            if segment not in current._children:
                # Use current.path for better error reporting, fallback to '/' for root
                current_node_path_str = str(current.path) if current.path else "/"
                raise NodeNotFoundError(f"Path segment '{segment}' not found in '{current_node_path_str}'")
            current = current._children[segment]

    return current


def remove(node: Node, path: str | NodePath) -> Node:
    """
    Resolves a path, detaches the subtree, and returns the detached node.
    Refuses to remove the root.
    """
    resolved_node = resolve(node, path)

    if resolved_node.parent is None:  # It's the root node
        raise InvalidTreeError("Cannot remove the root node.")

    # Detach will handle clearing parent/name and returning the node
    return resolved_node.parent.detach(resolved_node.name) # type: ignore


def absolute_path(node: Node) -> NodePath:
    """Returns the absolute NodePath for the given node."""
    if node.parent is None:
        return NodePath("/")

    path_segments = []
    current = node
    while current.parent:
        if current.name is None: # Should not happen for non-root nodes in a valid tree
            raise InvalidTreeError("Node with parent has no name.")
        path_segments.append(current.name)
        current = current.parent

    # Reverse to get the correct order and join with '/'
    return NodePath("/" + "/".join(reversed(path_segments)))


def relative_path(node: Node, target: Node) -> NodePath:
    """Returns the relative NodePath from node to target."""
    if node is target:
        return NodePath(".")

    # Check if they are in the same tree
    root_node = _get_root(node)
    root_target = _get_root(target)
    if root_node is not root_target:
        raise NotInSameTreeError("Cannot calculate relative path between nodes in different trees.")

    # Find the lowest common ancestor (LCA)
    node_ancestors = set(node.ancestors)
    node_ancestors.add(node)
    target_ancestors = set(target.ancestors)
    target_ancestors.add(target)

    lca = None
    # Start from node's ancestors and go up, checking if they are also target's ancestors
    current_node_path = node
    for anc in node.ancestors:
        if anc in target_ancestors:
            lca = anc
            break
        current_node_path = anc # This will be the LCA if no common ancestor found higher up

    # If LCA is not found through ancestor sets (e.g., one is ancestor of other),
    # then the LCA is the node itself or the target itself.
    if lca is None:
        if node in target_ancestors:
            lca = node
        elif target in node_ancestors:
            lca = target
        else:
            # This case should ideally not be reached if they are in the same tree
            # but as a fallback, consider the root if nothing else matches.
            lca = root_node


    # Path from node up to LCA
    path_up = []
    current = node
    while current is not lca:
        if current.name is None:
            raise InvalidTreeError("Node in path has no name.")
        path_up.append(current.name)
        current = current.parent # type: ignore
        if current is None: # Should not happen if LCA is found correctly
            raise InvalidTreeError("Unexpected tree structure during relative path calculation.")

    # Path from LCA down to target
    path_down = []
    current = target
    while current is not lca:
        if current.name is None:
            raise InvalidTreeError("Node in path has no name.")
        path_down.append(current.name)
        current = current.parent # type: ignore
        if current is None:
            raise InvalidTreeError("Unexpected tree structure during relative path calculation.")

    # Combine: '..' for path_up, then names for path_down
    relative_segments = [".."] * len(path_up) + list(reversed(path_down))
    return NodePath("/".join(relative_segments))


def ancestors(node: Node) -> tuple[Node, ...]:
    """Returns a tuple of ancestor nodes, from immediate parent to root."""
    ancestors_list = []
    current = node.parent
    while current:
        ancestors_list.append(current)
        current = current.parent
    return tuple(ancestors_list)


def descendants(node: Node) -> tuple[Node, ...]:
    """Returns a tuple of descendant nodes in depth-first, pre-order."""
    desc_list = []
    # Start traversal from children of the node, not the node itself
    for child_name, child_node in node._children.items():
        desc_list.append(child_node)
        # Recursively add descendants of this child
        desc_list.extend(descendants(child_node))
    return tuple(desc_list)


def siblings(node: Node) -> tuple[Node, ...]:
    """Returns a tuple of sibling nodes, in insertion order."""
    if node.parent is None:
        return ()
    
    sibling_list = []
    # Iterate through parent's children and add any that are not 'node'
    for child_name, child_node in node.parent._children.items():
        if child_node is not node:
            sibling_list.append(child_node)
    return tuple(sibling_list)


def leaves(node: Node) -> tuple[Node, ...]:
    """Returns a tuple of leaf nodes in depth-first order."""
    leaf_list = []
    if not node._children: # If the current node is a leaf
        leaf_list.append(node)
    else: # If it has children, recurse
        for child_node in node._children.values():
            leaf_list.extend(leaves(child_node))
    return tuple(leaf_list)
