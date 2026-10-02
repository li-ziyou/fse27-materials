from __future__ import annotations

from .model import Node, NodePath, NodeNotFoundError, InvalidTreeError, NotInSameTreeError


def resolve(node: Node, path: str | NodePath) -> Node:
    if not isinstance(path, NodePath):
        path = NodePath(path)

    current_node = node

    if path.is_absolute():
        # If the path is absolute, we need to find the root of the current node's tree.
        # This assumes that a node with no parent is the root.
        # If the provided path is just "/", it should resolve to the root.
        while current_node.parent is not None:
            current_node = current_node.parent
        
        if str(path) == "/":
            # If the path is absolute and just "/", it should resolve to the root.
            # We need to find the root of the current node's tree.
            root_node = node
            while root_node.parent is not None:
                root_node = root_node.parent
            return root_node
        
        # Remove the leading '/' for relative traversal from the root
        path_segments = path.parts[1:]
    else:
        path_segments = path.parts

    for segment in path_segments:
        if segment == ".":
            continue
        elif segment == "..":
            if current_node.parent is None:
                # Trying to go above the root
                raise NodeNotFoundError(f"Cannot resolve path '{path}': movement above root")
            current_node = current_node.parent
        elif segment in current_node.children:
            current_node = current_node.children[segment]
        else:
            raise NodeNotFoundError(f"Cannot resolve path '{path}': segment '{segment}' not found")

    return current_node


def remove(node: Node, path: str | NodePath) -> Node:
    target_node = resolve(node, path)

    if target_node.parent is None:
        raise InvalidTreeError("Cannot remove the root node.")

    # Detach the target node from its parent.
    # The detach function should handle clearing the parent and name of the detached node.
    return target_node.parent.detach(target_node.name)


def absolute_path(node: Node) -> NodePath:
    if node.parent is None:
        return NodePath("/")

    path_parts = []
    current = node
    while current.parent is not None:
        if current.name is None:
            # This should not happen in a valid tree structure where nodes have names
            # unless it's the root node itself, which is handled above.
            raise InvalidTreeError("Node in tree has no name but is not the root.")
        path_parts.append(current.name)
        current = current.parent

    path_parts.reverse()
    return NodePath("/" + "/".join(path_parts))


def relative_path(node: Node, target: Node) -> NodePath:
    if node == target:
        return NodePath(".")

    # If target is a new, unattached node, it cannot be in the same tree as 'node'.
    # If node is also unattached (a root), they are separate trees.
    # If node is attached, target is definitely not in its tree.
    if target.parent is None and target is not node:
        raise NotInSameTreeError("Cannot determine relative path to a node not in the same tree.")

    node_ancestors = {n for n in node.ancestors}
    node_ancestors.add(node)

    if target in node_ancestors:
        # Target is a descendant of node
        path_parts = []
        current = target
        while current.parent != node:
            if current.name is None:
                raise InvalidTreeError("Node in tree has no name but is not the root.")
            path_parts.append(current.name)
            current = current.parent
        path_parts.reverse()
        return NodePath("/".join(path_parts))
    else:
        # Find the lowest common ancestor
        node_path_parts = list(node.path.parts)
        target_path_parts = list(target.path.parts)

        common_len = 0
        for i in range(min(len(node_path_parts), len(target_path_parts))):
            if node_path_parts[i] == target_path_parts[i]:
                common_len += 1
            else:
                break

        # The check for different trees needs to be more robust.
        # If common_len == 0, it implies no shared path segments from the root.
        # We also need to ensure they originate from the same root node.
        # If target.parent is None and node.parent is None, they are separate roots.
        # If target.parent is None and node.parent is not None, they are in different trees.
        # If node.parent is None and target.parent is not None, they are in different trees.
        # The original check `node.path.root != target.path.root` is insufficient if target.path is not well-defined.
        # The check `target.parent is None and target is not node` at the beginning should handle most cases.
        # Let's refine the existing check to be more explicit about tree roots.

        # If we reach here, target is not a descendant and not the node itself.
        # We need to confirm they are in the same tree.
        # If either node has no parent, they are roots. If they are different roots, NotInSameTreeError.
        # If one has a parent and the other doesn't, NotInSameTreeError.
        node_is_root = node.parent is None
        target_is_root = target.parent is None

        if node_is_root != target_is_root: # One is root, the other isn't
            raise NotInSameTreeError("Cannot determine relative path between nodes in different trees.")
        elif node_is_root and target_is_root and node is not target: # Both are roots but different nodes
            raise NotInSameTreeError("Cannot determine relative path between nodes in different trees.")
        # If both are roots and the same node, it's handled by node == target.
        # If both are attached and share a root, common_len logic should work.

        # The original condition `common_len == 0 and node.path.root != target.path.root`
        # is still relevant if both have parents and share a root but have no common path segments (e.g. siblings of roots).
        # However, the added checks above should cover the 'different trees' scenario more reliably.
        # Let's re-evaluate the original condition in light of the new checks.
        # If we passed the initial checks, they are in the same tree.
        # The original condition `if common_len == 0 and node.path.root != target.path.root:`
        # seems to be designed to catch cases where paths don't align from the root.
        # However, if they are in the same tree, `node.path.root` and `target.path.root` should be the same.
        # So, `node.path.root != target.path.root` would be false if they are in the same tree.
        # This implies that the `common_len == 0` part might be the primary indicator when they *are* in the same tree,
        # but their paths diverge immediately.
        # Let's simplify the logic for clarity. If we've passed the initial checks, they are in the same tree.
        # The logic for LCA should then apply correctly.

        # The original check for different trees was:
        # if common_len == 0 and node.path.root != target.path.root:
        #     raise NotInSameTreeError("Cannot determine relative path between nodes in different trees.")
        # This condition is not met when target is Node() because target.path.root might be the same as node.path.root
        # or target.path is not properly defined.
        # The new checks at the start are more robust for identifying separate trees.
        # If we reach here, they are in the same tree, and the LCA logic should work.
        # The original `if common_len == 0 ...` block might be redundant or need adjustment if the new checks are sufficient.
        # For now, let's assume the new checks are enough to identify different trees.
        # If we passed the new checks, they are in the same tree.
        # The LCA logic should then correctly calculate the relative path.

        # Number of steps up from node to LCA
        steps_up = len(node_path_parts) - common_len
        # Path from LCA to target
        steps_down = target_path_parts[common_len:]

        relative_parts = [".."] * steps_up + steps_down
        return NodePath("/".join(relative_parts))



def ancestors(node: Node) -> tuple[Node, ...]:
    if node.parent is None:
        return ()

    ancestor_list = []
    current = node.parent
    while current is not None:
        ancestor_list.append(current)
        current = current.parent
    return tuple(ancestor_list)


def descendants(node: Node) -> tuple[Node, ...]:
    all_descendants = []
    
    def _traverse(current_node: Node):
        for child in current_node.children.values():
            all_descendants.append(child)
            _traverse(child)

    _traverse(node)
    return tuple(all_descendants)


def siblings(node: Node) -> tuple[Node, ...]:
    if node.parent is None:
        return ()

    return tuple(
        child for name, child in node.parent.children.items() if child is not node
    )


def leaves(node: Node) -> tuple[Node, ...]:
    leaf_list = []

    def _traverse(current_node: Node):
        if not current_node.children:
            leaf_list.append(current_node)
            return
        for child in current_node.children.values():
            _traverse(child)

    _traverse(node)
    return tuple(leaf_list)
