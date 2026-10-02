from __future__ import annotations

from .model import Node, NodePath, NodeNotFoundError, NotInSameTreeError


def resolve(node: Node, path: str | NodePath) -> Node:
    if not path:
        return node

    current_path = NodePath(path)
    current_node = node

    if current_path.is_absolute():
        # If the path is absolute, we need to find the root first.
        # This assumes the root has no parent.
        while current_node.parent is not None:
            current_node = current_node.parent
        segments = current_path.parts[1:]  # Skip the initial '/'
    else:
        segments = current_path.parts

    for segment in segments:
        if segment == ".":
            continue
        elif segment == "..":
            if current_node.parent is None:
                raise NodeNotFoundError(f"Cannot resolve '{path}': movement above root")
            current_node = current_node.parent
        elif segment in current_node.children:
            current_node = current_node.children[segment]
        else:
            raise NodeNotFoundError(f"Cannot resolve '{path}': segment '{segment}' not found")

    return current_node


def remove(node: Node, path: str | NodePath) -> Node:
    from .structure import detach  # Import detach from structure

    # TN-B2: refuse to remove the root
    target_node = node.resolve(path)
    
    if target_node.parent is None:
        # If the resolved node is the root, we cannot remove it.
        raise NodeNotFoundError("Cannot remove the root node")

    # Detach the target node. The detach function should handle clearing parent/name.
    # We need to call detach on the parent of the target_node.
    parent_of_target = target_node.parent
    if parent_of_target is None:
        # This case should be caught by the root check above, but as a safeguard
        # This might happen if target_node is root, which is already handled.
        # Or if somehow target_node has no parent but is not root (invalid tree state).
        raise NodeNotFoundError("Target node has no parent to detach from")
        
    detached_node = detach(parent_of_target, target_node.name)
    
    # TN-B2: detaches that complete subtree
    # The detach function is responsible for this. We just return the detached node.
    return detached_node


def absolute_path(node: Node) -> NodePath:
    if node.parent is None:
        return NodePath("/")
    
    path_segments = []
    current = node
    while current.parent is not None:
        if current.name is None:
            # This should not happen in a valid tree structure
            raise InvalidTreeError("Node with parent has no name")
        path_segments.append(current.name)
        current = current.parent
    
    return NodePath("/" + "/".join(reversed(path_segments)))


def relative_path(node: Node, target: Node) -> NodePath:
    if node is target:
        return NodePath(".")

    # Check if nodes are in the same tree by finding their roots
    node_root = node
    while node_root.parent:
        node_root = node_root.parent
    
    target_root = target
    while target_root.parent:
        target_root = target_root.parent
        
    if node_root is not target_root:
        raise NotInSameTreeError("Nodes are not in the same tree")

    # Find the lowest common ancestor (LCA)
    node_path_list = [node] + list(node.ancestors)
    target_path_list = [target] + list(target.ancestors)
    
    common_ancestor = None
    # Iterate from root downwards
    for n_anc, t_anc in zip(reversed(node_path_list), reversed(target_path_list)):
        if n_anc is t_anc:
            common_ancestor = n_anc
        else:
            break
    
    if common_ancestor is None:
        # This should not happen if they are in the same tree and have a common root.
        # This could occur if node or target is the root and the other is not, and LCA logic failed.
        # Or if node and target are distinct roots of different trees (already handled above).
        # Let's re-evaluate this scenario. If node_root == target_root, there MUST be an LCA.
        # If common_ancestor is still None, it means node_path_list and target_path_list did not align at all,
        # which contradicts being in the same tree.
        raise InvalidTreeError("Could not find common ancestor in the same tree")

    # Path from node up to common ancestor
    path_up_segments = []
    current = node
    while current is not common_ancestor:
        if current.name is None:
            raise InvalidTreeError("Node in path to LCA has no name")
        path_up_segments.append(current.name)
        current = current.parent
        if current is None: # Should not happen if common_ancestor is found correctly
            raise InvalidTreeError("Unexpectedly lost parent during path calculation to LCA")
            
    # Path from common ancestor down to target
    path_down_segments = []
    current = target
    while current is not common_ancestor:
        if current.name is None:
            raise InvalidTreeError("Node in path from LCA has no name")
        path_down_segments.append(current.name)
        current = current.parent
        if current is None: # Should not happen if common_ancestor is found correctly
            raise InvalidTreeError("Unexpectedly lost parent during path calculation from LCA")
            
    # Construct the relative path
    # Number of ".." needed is the number of segments to go up
    num_levels_up = len(path_up_segments)
    relative_path_parts = [".."] * num_levels_up
    
    # Add the segments from common ancestor down to target
    # path_down_segments are collected from target up to LCA, so need to be reversed
    relative_path_parts.extend(reversed(path_down_segments))
    
    # If the list is empty, it means node is the common ancestor and target is also the common ancestor (node == target), which is handled.
    # Or node is LCA and target is a child (path_up_segments is empty, path_down_segments has target's name).
    # Or target is LCA and node is a child (path_down_segments is empty, path_up_segments has node's name) -> this case should not happen if LCA is correct.
    # If node is LCA, path_up_segments is empty, and we just return path_down.
    if not relative_path_parts:
        return NodePath(".") # Should be covered by node is target case

    return NodePath("/".join(relative_path_parts))


def ancestors(node: Node) -> tuple[Node, ...]:
    if node.parent is None:
        return ()
    
    parent_nodes = []
    current = node.parent
    while current is not None:
        parent_nodes.append(current)
        current = current.parent
    return tuple(parent_nodes)


def descendants(node: Node) -> tuple[Node, ...]:
    # Depth-first pre-order traversal
    result = []
    
    def traverse(current_node: Node):
        # Add children first, then recurse into them
        for child_name in sorted(current_node.children.keys()): # Ensure deterministic order for tests
            child = current_node.children[child_name]
            result.append(child)
            traverse(child)

    # We need to traverse starting from the children of the given node
    # if the given node itself should not be included in the descendants.
    # The test case `test_traversal_views_have_the_disclosed_order` implies
    # that `root.descendants` includes all nodes except root, and `x.descendants`
    # would be empty if x has no children. This means `descendants` should
    # return the children and their descendants.
    
    # Let's re-read the test: `root.descendants == (a, x, y, b, z)`
    # This means the root itself is NOT included.
    # So, the traversal should start from the children of the `node`.
    
    for child_name in sorted(node.children.keys()):
        child = node.children[child_name]
        result.append(child)
        traverse(child)
        
    return tuple(result)


def siblings(node: Node) -> tuple[Node, ...]:
    if node.parent is None:
        return ()
    
    parent_children = node.parent.children
    sibling_nodes = [child for name, child in parent_children.items() if child is not node]
    
    # The test case implies insertion order, which is what dict iteration gives in modern Python.
    # Sorting by name for deterministic results if needed, but the test implies dict order is fine.
    # For now, let's rely on dict order.
    return tuple(sibling_nodes)


def leaves(node: Node) -> tuple[Node, ...]:
    result = []
    
    def traverse(current_node: Node):
        if not current_node.children:
            result.append(current_node)
            return
        
        for child_name in sorted(current_node.children.keys()):
            traverse(current_node.children[child_name])

    # The test case `root.leaves == (x, y, z)` implies we should traverse from the root's children.
    # If `node` itself is a leaf, it should be included.
    # Let's adjust the logic to start traversal from `node` itself.
    
    if not node.children: # if the node itself is a leaf
        return (node,)
        
    for child_name in sorted(node.children.keys()):
        traverse(node.children[child_name])
        
    return tuple(result)

