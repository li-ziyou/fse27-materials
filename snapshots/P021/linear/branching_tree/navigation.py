from __future__ import annotations

from .model import Node, NodePath, NodeNotFoundError, NotInSameTreeError


def resolve(node: Node, path: str | NodePath) -> Node:
    if isinstance(path, str):
        path = NodePath(path)

    if path.is_absolute():
        # Start from the root if the path is absolute
        current = node
        while current.parent is not None:
            current = current.parent
        # Remove the leading '/' from path.parts if it exists
        if path.parts and path.parts[0] == '/':
            path = NodePath(*path.parts[1:])
    else:
        current = node

    for segment in path.parts:
        if segment == ".":
            continue
        elif segment == "..":
            if current.parent is None:
                raise NodeNotFoundError("Cannot resolve '..' above the root.")
            current = current.parent
        elif segment in current.children:
            current = current.children[segment]
        else:
            raise NodeNotFoundError(f"Segment '{segment}' not found in path '{path}'.")
    return current


def remove(node: Node, path: str | NodePath) -> Node:
    # TN-B2: remove resolves a path, detaches that complete subtree, and refuses to remove the root.
    target_node = node.resolve(path)
    if target_node.parent is None and target_node.name is None: # Check if it's the root node
        raise InvalidTreeError("Cannot remove the root node.")
    
    if target_node.parent:
        return target_node.parent.detach(target_node.name)
    else:
        # This case should ideally not be reached if the root check is correct,
        # but as a safeguard, if it's not the root and has no parent, it's orphaned.
        # Detaching an orphaned node means returning it without changing any parent.
        # However, the requirement is to detach it, implying it was attached.
        # If it's already orphaned, the operation might be considered a no-op or an error.
        # Given the context of removing a subtree, if it's already orphaned, it's effectively removed from any tree.
        # The function is expected to return the detached node.
        # If it has no parent, it's already detached. We should clear its name and return it.
        # This part needs careful consideration based on how orphaned nodes are handled.
        # For now, assuming it should be detached from its (non-existent) parent, we'll clear its metadata.
        target_node._parent = None
        target_node._name = None
        return target_node


def absolute_path(node: Node) -> NodePath:
    # TN-B3: path returns an absolute path
    if node.parent is None and node.name is None: # It's the root node
        return NodePath("/")

    path_segments = []
    current = node
    while current.parent is not None:
        if current.name is None: # Should not happen for non-root nodes
            raise InvalidTreeError("Node has a parent but no name.")
        path_segments.append(current.name)
        current = current.parent
    
    return NodePath("/" + "/".join(reversed(path_segments)))


def relative_path(node: Node, target: Node) -> NodePath:
    # TN-B3: relative_path_to returns a correct relative path for nodes in the same tree; separate trees raise NotInSameTreeError.
    if node is target:
        return NodePath(".")

    node_ancestors = node.ancestors
    target_ancestors = target.ancestors

    # Check if they are in the same tree by comparing their root ancestors
    # A simple way is to check if either node is an ancestor of the other, or if they share a common ancestor up to the root.
    # If node.path and target.path are absolute, they should start with the same root if in the same tree.
    # However, NodePath doesn't inherently store tree identity. The check needs to be more robust.
    # A common ancestor check is more reliable.
    
    # Find the lowest common ancestor (LCA)
    common_ancestor = None
    node_path_list = [node] + list(node_ancestors)
    target_path_list = [target] + list(target_ancestors)

    # Reverse lists to compare from root downwards
    node_path_list.reverse()
    target_path_list.reverse()

    for n_node, t_node in zip(node_path_list, target_path_list):
        if n_node is t_node:
            common_ancestor = n_node
        else:
            break
    
    if common_ancestor is None:
        raise NotInSameTreeError("Nodes are not in the same tree.")

    # If the common ancestor is the target node, then the node is a descendant of the target.
    # The relative path is simply the path segments from the target down to the node.
    if common_ancestor is target:
        path_down_segments = []
        current = node
        while current is not target:
            if current.name is None:
                raise InvalidTreeError("Internal error: Name missing during relative path calculation.")
            path_down_segments.append(current.name)
            current = current.parent
        return NodePath("/".join(reversed(path_down_segments)))
        
    # Calculate path from node up to LCA
    path_up_segments = []
    current = node
    while current is not common_ancestor:
        if current.parent is None: # Should not happen if common_ancestor is found
            raise InvalidTreeError("Internal error: Parent missing during relative path calculation.")
        path_up_segments.append("..")
        current = current.parent

    # Calculate path from LCA down to target
    path_down_segments = []
    current = target
    while current is not common_ancestor:
        if current.name is None: # Should not happen for non-root nodes
            raise InvalidTreeError("Internal error: Name missing during relative path calculation.")
        path_down_segments.append(current.name)
        current = current.parent
    
    # Combine paths
    relative_path_parts = path_up_segments + list(reversed(path_down_segments))
    
    return NodePath("/".join(relative_path_parts))


def ancestors(node: Node) -> tuple[Node, ...]:
    # TN-B4: ancestors reflect the current tree and return tuples.
    if node.parent is None: # Root node has no ancestors
        return ()
    
    ancestors_list = []
    current = node.parent
    while current is not None:
        ancestors_list.append(current)
        current = current.parent
    
    return tuple(ancestors_list)


def descendants(node: Node) -> tuple[Node, ...]:
    # TN-B4: depth-first pre-order descendants
    all_descendants = []
    
    def traverse(current_node: Node):
        for child_name in sorted(current_node.children.keys()): # Ensure consistent order
            child = current_node.children[child_name]
            all_descendants.append(child)
            traverse(child)
            
    traverse(node)
    return tuple(all_descendants)


def siblings(node: Node) -> tuple[Node, ...]:
    # TN-B4: insertion-ordered siblings
    if node.parent is None:
        return () # Root node has no siblings
    
    parent_children = node.parent.children
    # Return all children of the parent except the node itself, maintaining insertion order.
    # The children dict is insertion-ordered in Python 3.7+.
    return tuple(child for name, child in parent_children.items() if child is not node)


def leaves(node: Node) -> tuple[Node, ...]:
    # TN-B4: depth-first leaves
    all_leaves = []

    def traverse(current_node: Node):
        if not current_node.children: # If it's a leaf node
            all_leaves.append(current_node)
            return
        
        for child_name in sorted(current_node.children.keys()): # Ensure consistent order
            child = current_node.children[child_name]
            traverse(child)
            
    traverse(node)
    return tuple(all_leaves)
