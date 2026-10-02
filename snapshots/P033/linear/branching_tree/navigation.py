from __future__ import annotations

from .model import Node, NodePath


def resolve(node: Node, path: str | NodePath) -> Node:
    """TN-B1: Resolve absolute or relative path."""
    if not isinstance(path, NodePath):
        path = NodePath(path)

    # If path is absolute, start from the root. Otherwise, start from the current node.
    current_node = node if not path.is_absolute() else node.parent  # This will need to be adjusted if node is root

    # If it's an absolute path, we need to find the root of the tree.
    # A node's parent is None only if it's the root.
    if path.is_absolute():
        root = node
        while root.parent is not None:
            root = root.parent
        current_node = root
    else:
        current_node = node

    # Handle '.' and '..'
    components = list(path.parts)
    
    # If the path is just '/', return the root.
    if path == NodePath('/') and current_node.parent is None:
        return current_node
    
    # If the path is relative and starts with '/', it's actually absolute.
    if not path.is_absolute() and components[0] == '/':
        current_node = node # Reset to node if it was incorrectly set to parent
        root = node
        while root.parent is not None:
            root = root.parent
        current_node = root
        components = components[1:] # Remove the leading '/'

    for component in components:
        if component == ".":
            continue
        elif component == "..":
            if current_node.parent is None:
                raise NodeNotFoundError("Cannot go above root")
            current_node = current_node.parent
        else:
            if component not in current_node._children:
                raise NodeNotFoundError(f"Component '{component}' not found in path '{path}'")
            current_node = current_node._children[component]
    
    return current_node


def remove(node: Node, path: str | NodePath) -> Node:
    """TN-B2: Resolve path and detach the subtree."""
    target_node = resolve(node, path)
    
    # TN-B2: Refuse to remove the root
    if target_node.parent is None:
        raise InvalidTreeError("Cannot remove the root node")
    
    return target_node.orphan()


def absolute_path(node: Node) -> NodePath:
    """TN-B3: Return the absolute path of the node."""
    if node.parent is None:
        return NodePath("/")
    
    path_parts = []
    current = node
    while current.parent is not None:
        path_parts.append(current.name)
        current = current.parent
    
    # Reverse the parts and join them with '/'
    return NodePath("/" + "/".join(reversed(path_parts)))


def relative_path(node: Node, target: Node) -> NodePath:
    """TN-B3: Return the relative path from node to target."""
    if node.parent is None and target.parent is None:
        # Both are roots of separate trees (or the same root)
        if node is target:
            return NodePath(".")
        else:
            raise NotInSameTreeError("Cannot get relative path between different root nodes")
    
    # Check if they are in the same tree
    node_root = node
    while node_root.parent is not None:
        node_root = node_root.parent
    
    target_root = target
    while target_root.parent is not None:
        target_root = target_root.parent

    if node_root is not target_root:
        raise NotInSameTreeError("Nodes are not in the same tree")

    # If target is self
    if node is target:
        return NodePath(".")

    # If target is a child or descendant
    if target.parent is node:
        return NodePath(target.name)
    
    # If node is a child or descendant of target
    if node.parent is target:
        return NodePath("..")
    
    # General case: find common ancestor
    node_ancestors = set(node.ancestors)
    target_ancestors = set(target.ancestors)
    
    common_ancestor = None
    current_node_for_common = node
    while current_node_for_common is not None:
        if current_node_for_common in target_ancestors:
            common_ancestor = current_node_for_common
            break
        current_node_for_common = current_node_for_common.parent
    
    if common_ancestor is None:
        # This should ideally not happen if they are in the same tree and not root
        # but as a fallback, we can assume they are in different trees.
        raise NotInSameTreeError("Could not find common ancestor")

    # Path from node up to common ancestor
    path_up = []
    current = node
    while current is not common_ancestor:
        path_up.append(current.name)
        current = current.parent
    
    # Path from common ancestor down to target
    path_down = []
    current = target
    while current is not common_ancestor:
        path_down.append(current.name)
        current = current.parent
    
    # Combine paths: '..' for each step up, then path down
    relative_parts = [".."] * len(path_up) + list(reversed(path_down))
    
    return NodePath("/".join(relative_parts))



def ancestors(node: Node) -> tuple[Node, ...]:
    """TN-B4: Return ancestors in order from parent to root."""
    result = []
    current = node._parent
    while current is not None:
        result.append(current)
        current = current._parent
    return tuple(result)


def descendants(node: Node) -> tuple[Node, ...]:
    """TN-B4: Return depth-first pre-order descendants."""
    result = []
    
    def traverse(n: Node) -> None:
        # Iterate over children in insertion order
        for name in n._children:
            child = n._children[name]
            result.append(child)
            traverse(child)
    
    # Start traversal from the children of the given node, not the node itself
    # as per typical 'descendants' definition. If the node itself should be included,
    # then 'result.append(node)' would be needed before traverse(node).
    # Based on test_traversal_views_have_the_disclosed_order, the node itself is not included.
    traverse(node)
    return tuple(result)


def siblings(node: Node) -> tuple[Node, ...]:
    """TN-B4: Return insertion-ordered siblings (excluding self)."""
    if node._parent is None:
        return ()
    
    parent = node._parent
    result = []
    # Iterate over children in insertion order
    for name in parent._children:
        child = parent._children[name]
        if child is not node:
            result.append(child)
    
    return tuple(result)


def leaves(node: Node) -> tuple[Node, ...]:
    """TN-B4: Return depth-first leaf nodes."""
    result = []
    
    def traverse(n: Node) -> None:
        if not n._children:
            result.append(n)
        else:
            # Iterate over children in insertion order
            for name in n._children:
                traverse(n._children[name])
    
    traverse(node)
    return tuple(result)
