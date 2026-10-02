from __future__ import annotations

from .model import Node, NodeNotFoundError, NodePath, NotInSameTreeError


def resolve(node: Node, path: str | NodePath) -> Node:
    current = node
    if isinstance(path, str):
        path = NodePath(path)

    if path.is_absolute():
        # Traverse from root if path is absolute
        while current.parent is not None:
            current = current.parent
    
    # Skip the root segment if it's absolute path
    path_segments = list(path.parts)
    if path.is_absolute() and path_segments and path_segments[0] == '/':
        path_segments = path_segments[1:]

    for segment in path_segments:
        if segment == ".":
            continue
        elif segment == "..":
            if current.parent is None:
                raise NodeNotFoundError("Cannot go above root")
            current = current.parent
        else:
            if segment not in current.children:
                raise NodeNotFoundError(f"Segment '{segment}' not found in path")
            current = current.children[segment]
    return current


def remove(node: Node, path: str | NodePath) -> Node:
    if isinstance(path, str):
        path = NodePath(path)

    if path.name == "..":
        raise InvalidTreeError("Cannot remove root or parent")
    
    target_node = resolve(node, path)
    
    if target_node.parent is None and target_node is node:
        raise InvalidTreeError("Cannot remove the root node")
        
    parent = target_node.parent
    if parent:
        del parent._children[target_node.name]
        target_node._parent = None
        target_node._name = None
    return target_node


def absolute_path(node: Node) -> NodePath:
    if node.parent is None:
        return NodePath("/")
    
    path_parts = []
    current = node
    while current.parent is not None:
        path_parts.append(current.name)
        current = current.parent
    
    return NodePath("/" + "/".join(reversed(path_parts)))


def relative_path(node: Node, target: Node) -> NodePath:
    if node is target:
        return NodePath(".")

    # Get ancestors including the node itself to easily find common ancestor
    node_ancestors_list = [node] + list(node.ancestors)
    target_ancestors_list = [target] + list(target.ancestors)

    # Determine root for tree check
    node_root = node.path.root if node.parent else None
    target_root = target.path.root if target.parent else None

    if node_root != target_root:
        raise NotInSameTreeError("Nodes are in different trees")

    # Find the lowest common ancestor
    common_ancestor = None
    for node_anc in reversed(node_ancestors_list):
        if node_anc in target_ancestors_list:
            common_ancestor = node_anc
            break

    if common_ancestor is None:
        # This should not happen if nodes are in the same tree and not the root
        raise NotInSameTreeError("Could not find a common ancestor")

    # Path from node up to the common ancestor
    path_up = []
    current = node
    while current is not common_ancestor:
        path_up.append("..")
        current = current.parent

    # Path from common ancestor down to the target
    path_down = []
    current = target
    while current is not common_ancestor:
        path_down.append(current.name)
        current = current.parent
    
    # Reverse path_down as we collected names from target up to common ancestor's child
    return NodePath("/".join(path_up + list(reversed(path_down))))


def ancestors(node: Node) -> tuple[Node, ...]:
    if node.parent is None:
        return ()  # Root node has no ancestors
    
    # The path.parents property already provides the ancestors as NodePath objects.
    # We need to resolve them back to Node objects.
    # Note: node.path.parents does NOT include the root node itself.
    # We also need to ensure we don't include the node itself in the ancestors list.
    
    # Get the absolute path of the node
    node_abs_path = absolute_path(node)
    
    # Get all parent paths from the NodePath object
    parent_paths = list(node_abs_path.parents)
    
    # Resolve each parent path to a Node object
    ancestor_nodes = []
    # We need to start from the root to resolve paths correctly if node.path.parents
    # does not provide the full path from the root node.
    # A safer approach is to traverse up from the node itself.
    current = node.parent
    while current:
        ancestor_nodes.append(current)
        current = current.parent
        
    # Ensure we are returning Node objects, not NodePaths
    return tuple(ancestor_nodes)


def descendants(node: Node) -> tuple[Node, ...]:
    result = []
    # Use a stack for depth-first traversal (pre-order)
    nodes_to_visit = list(node.children.values())
    nodes_to_visit.reverse() # Reverse to process in insertion order when popping
    while nodes_to_visit:
        current = nodes_to_visit.pop()
        result.append(current)
        # Add children in reverse order to maintain correct pre-order when popping
        children = list(current.children.values())
        children.reverse()
        nodes_to_visit.extend(children)
    return tuple(result)


def siblings(node: Node) -> tuple[Node, ...]:
    if node.parent is None:
        return ()
    return tuple(child for name, child in node.parent.children.items() if child is not node)


def leaves(node: Node) -> tuple[Node, ...]:
    result = []
    
    def find_leaves(current_node):
        if not current_node.children:
            result.append(current_node)
        else:
            for child in current_node.children.values():
                find_leaves(child)

    find_leaves(node)
    return tuple(result)

