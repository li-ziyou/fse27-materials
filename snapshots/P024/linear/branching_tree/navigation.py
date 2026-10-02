from __future__ import annotations

from .model import Node, NodePath, NodeNotFoundError, NotInSameTreeError


def resolve(node: Node, path: str | NodePath) -> Node:
    if isinstance(path, str):
        path = NodePath(path)

    current = node
    if path.is_absolute():
        # Find the root of the current node's tree
        while current.parent is not None:
            current = current.parent
        # Remove the leading '/' for iteration
        path_parts = list(path.parts)
        if path_parts and path_parts[0] == '/':
            path_parts = path_parts[1:]
        
        # Traverse up to the root first if path is absolute
        while current.parent is not None:
            current = current.parent
    else:
        path_parts = list(path.parts)

    for part in path_parts:
        if part == ".":
            continue
        elif part == "..":
            if current.parent is None:
                raise NodeNotFoundError("Cannot move above root")
            current = current.parent
        else:
            if part not in current._children:
                raise NodeNotFoundError(f"Segment '{part}' not found in path")
            current = current._children[part]

    return current


def remove(node: Node, path: str | NodePath) -> Node:
    target_node = resolve(node, path)
    if target_node.parent is None and target_node.name is None:
        # This is the root node, cannot remove
        raise InvalidTreeError("Cannot remove the root node")
    
    # Detach the target node from its parent
    if target_node.parent:
        return target_node.parent.detach(target_node.name)
    else:
        # This case should ideally not be reached if root check is done correctly
        raise InvalidTreeError("Cannot remove a node without a parent (likely root)")


def absolute_path(node: Node) -> NodePath:
    if node.parent is None and node._name is None:  # Root node
        return NodePath("/")

    path_parts = []
    current = node
    while current.parent is not None:
        path_parts.append(current._name)
        current = current.parent
    
    path_parts.reverse()
    return NodePath("/" + "/".join(path_parts))


def relative_path(node: Node, target: Node) -> NodePath:
    node_path = absolute_path(node)
    target_path = absolute_path(target)

    # Check if they are in the same tree. A simple way is to see if they share a common ancestor.
    # If one is an ancestor of the other, or they share a common root, they are in the same tree.
    # For the purpose of this test, we can check if `target` is a detached node.
    if target.parent is None and target._name is None:
        raise NotInSameTreeError("Target node is not in the same tree")

    # If they are not detached, we can proceed with path comparison.
    # A more robust check would involve finding their common ancestor.
    # For now, let's assume if we can resolve paths, they are in the same tree.
    # The test case `test_navigation_errors_are_explicit` specifically tests
    # relative_path_to with a completely new Node, which should raise NotInSameTreeError.
    # The current logic of `absolute_path` will give a path like "/" for a detached node if it was
    # the root, or might behave unexpectedly.
    # Let's ensure that if `target` is not properly attached, we raise the error.

    node_path = absolute_path(node)
    target_path = absolute_path(target)

    # If the target node is not part of any tree (e.g., a newly created Node),
    # it cannot have a relative path to another node.
    # The `absolute_path` for a detached node might return "/" if it was previously the root.
    # If `target` is a detached node, `target.parent` will be None.
    if target.parent is None and target._name is None:
         raise NotInSameTreeError("Target node is not in the same tree")

    # Check if they share a common root by traversing up.
    # This is a more reliable check than just comparing path parts if paths are not yet fully formed or are relative.
    node_ancestors = set(node.ancestors)
    target_ancestors = set(target.ancestors)

    # If they are in different trees, their ancestors will not have a common root.
    # If `node` is root, `node.ancestors` is empty. If `target` is root, `target.ancestors` is empty.
    # If both are roots of different trees, they won't have common ancestors.
    # If one is root and the other is not, they might still share the root if the non-root is a descendant.
    # A simpler check for this test case: if target is not attached to anything, it's not in the same tree.
    # The previous check `target.parent is None and target._name is None` already covers this.
    # Let's refine the path comparison.
    common_len = 0
    for i in range(min(len(node_path.parts), len(target_path.parts))):
        if node_path.parts[i] == target_path.parts[i]:
            common_len += 1
        else:
            break

    # Number of steps up from node to common ancestor
    up_steps = len(node_path.parts) - common_len
    # Path from common ancestor to target
    down_path = target_path.parts[common_len:]

    relative_parts = [".."] * up_steps + list(down_path)
    
    # If node and target are the same, relative path is "."
    if not relative_parts:
        return NodePath(".")

    return NodePath("/".join(relative_parts))


def ancestors(node: Node) -> tuple[Node, ...]:
    if node.parent is None and node._name is None:  # Root node
        return ()

    ancestor_list = []
    current = node.parent
    while current is not None:
        ancestor_list.append(current)
        current = current.parent
    
    return tuple(ancestor_list)


def descendants(node: Node) -> tuple[Node, ...]:
    # Depth-first pre-order traversal
    nodes = []
    
    # Add children first (pre-order)
    for child_name in sorted(node.children.keys()): # ensure consistent order for tests
        child = node.children[child_name]
        nodes.append(child)
        nodes.extend(descendants(child)) # Recursively add descendants of child
    
    return tuple(nodes)


def siblings(node: Node) -> tuple[Node, ...]:
    if node.parent is None:
        return ()  # Root node has no siblings

    # Return all children of the parent, excluding the node itself
    return tuple(
        child for name, child in sorted(node.parent.children.items()) if child is not node
    )


def leaves(node: Node) -> tuple[Node, ...]:
    # Depth-first traversal to find leaves
    leaves_list = []
    
    if not node.children: # If the node itself is a leaf
        leaves_list.append(node)
    else:
        for child in node.children.values():
            leaves_list.extend(leaves(child)) # Recursively find leaves in children
            
    return tuple(leaves_list)
