from __future__ import annotations

from .model import Node, NodePath, NodeNotFoundError, NotInSameTreeError


def resolve(node: Node, path: str | NodePath) -> Node:
    current_node = node
    path_obj = NodePath(path)

    if path_obj.is_absolute():
        # If the path is absolute, we start from the root of the tree.
        # We need to find the root of the current node's tree.
        while current_node.parent is not None:
            current_node = current_node.parent
        
        # Remove the leading '/' for component iteration
        components = list(path_obj.parts)[1:]
    else:
        # If the path is relative, we start from the current node.
        components = path_obj.parts

    for component in components:
        if component == ".":
            continue
        elif component == "..":
            if current_node.parent is None:
                raise NodeNotFoundError("Cannot move above the root node")
            current_node = current_node.parent
        else:
            if component not in current_node._children:
                raise NodeNotFoundError(f"Node '{component}' not found in path")
            current_node = current_node._children[component]
    
    return current_node


def remove(node: Node, path: str | NodePath) -> Node:
    if node.parent is None and node.path == NodePath("/"): # Check if it's the root node
        # Special case: cannot remove the root node itself
        path_obj = NodePath(path)
        if path_obj == NodePath("/") or path_obj == NodePath("."):
             raise ValueError("Cannot remove the root node")

    target_node = resolve(node, path)
    
    if target_node.parent is None: # This means target_node is the root of the tree
        raise ValueError("Cannot remove the root node")

    # Detach the target node and its subtree
    # The detach function is called on the parent of the node to be detached.
    parent_of_target = target_node.parent
    if parent_of_target is None:
        # This should not happen if target_node is not the root, which is checked above.
        raise InvalidTreeError("Target node has no parent but is not root.")
    
    # The name of the child to detach is the name of the target_node itself.
    detached_node = parent_of_target.detach(target_node.name) # type: ignore
    
    # The detach function already clears parent and name, and returns the detached node.
    # We need to ensure the returned node is the one that was at the specified path.
    return detached_node


def absolute_path(node: Node) -> NodePath:
    if node.parent is None:
        return NodePath("/")  # Root node

    path_parts = []
    current = node
    while current.parent is not None:
        if current.name is None:
            # This should not happen for a node that is part of a tree
            raise InvalidTreeError("Node has a parent but no name")
        path_parts.append(current.name)
        current = current.parent
    
    return NodePath("/" + "/".join(reversed(path_parts)))


def relative_path(node: Node, target: Node) -> NodePath:
    if node is target:
        return NodePath(".")

    node_ancestors = set(node.ancestors)
    target_ancestors = set(target.ancestors)

    if node.parent is None and target.parent is None and node is not target:
        raise NotInSameTreeError("Nodes are not in the same tree")
    
    # Check if they are in the same tree by seeing if one is an ancestor of the other
    if target in node_ancestors or node in target_ancestors:
        # If target is a descendant of node
        if target in node_ancestors:
            target_path_parts = []
            current = target
            while current is not node:
                if current.name is None:
                    raise InvalidTreeError("Node in target path has no name")
                target_path_parts.append(current.name)
                current = current.parent
            return NodePath("/".join(reversed(target_path_parts)))

        # If node is a descendant of target
        if node in target_ancestors:
            common_ancestor = target
            steps_up = 0
            current = node
            while current is not common_ancestor:
                steps_up += 1
                current = current.parent
            
            path_parts = [".."] * steps_up
            
            current = target
            while current is not common_ancestor:
                if current.name is None:
                    raise InvalidTreeError("Node in source path has no name")
                path_parts.append(current.name)
                current = current.parent
            return NodePath("/".join(path_parts))

    # If they are not direct ancestors/descendants, find the common ancestor
    node_path_parts = list(node.path.parts)
    target_path_parts = list(target.path.parts)

    common_len = 0
    while common_len < len(node_path_parts) and common_len < len(target_path_parts) and node_path_parts[common_len] == target_path_parts[common_len]:
        common_len += 1

    # If common_len is 0, it means the common ancestor is the root, but they are not in the same tree.
    # This check is covered by the initial NotInSameTreeError check, but as a safeguard:
    if common_len == 0 and node.path.parts[0] != target.path.parts[0]:
         raise NotInSameTreeError("Nodes are not in the same tree")

    # Steps up from node to common ancestor
    steps_up = len(node_path_parts) - common_len
    path_parts = [".."] * steps_up

    # Steps down from common ancestor to target
    path_parts.extend(target_path_parts[common_len:])
    
    return NodePath("/".join(path_parts))


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
    # Depth-first pre-order traversal
    result = []
    nodes_to_visit = list(node.children.values())
    
    while nodes_to_visit:
        current = nodes_to_visit.pop(0) # Use pop(0) for pre-order (BFS-like for children, but DFS overall)
        result.append(current)
        # Add children in reverse order to maintain insertion order for iteration
        children_items = list(current.children.items())
        children_items.reverse()
        for name, child_node in children_items:
            nodes_to_visit.insert(0, child_node)
    return tuple(result)


def siblings(node: Node) -> tuple[Node, ...]:
    if node.parent is None:
        return ()
    
    parent_children = list(node.parent.children.values())
    return tuple(sibling for sibling in parent_children if sibling is not node)


def leaves(node: Node) -> tuple[Node, ...]:
    # Depth-first traversal to find leaves
    result = []
    
    def find_leaves(current_node: Node):
        if not current_node.children:
            result.append(current_node)
            return
        
        for child_name in current_node.children:
            find_leaves(current_node.children[child_name])

    find_leaves(node)
    return tuple(result)
