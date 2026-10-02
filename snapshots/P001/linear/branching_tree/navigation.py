from __future__ import annotations

from .model import Node, InvalidTreeError, NodeNotFoundError, NodePath, NotInSameTreeError
from .structure import detach


def absolute_path(node: Node) -> NodePath:
    """TN-B3: returns an absolute path"""
    if node.parent is None:
        return NodePath("/")
    path_parts = []
    current = node
    while current.parent is not None:
        path_parts.append(current.name)
        current = current.parent
    return NodePath("/" + "/".join(reversed(path_parts)))


def relative_path(node: Node, target: Node) -> NodePath:
    """TN-B3: returns a relative path"""
    if node is target:
        return NodePath(".")

    node_ancestors = set(node.ancestors)
    target_ancestors = set(target.ancestors)

    if node.parent is not target.parent and node_ancestors.isdisjoint(target_ancestors):
        raise NotInSameTreeError("Nodes are not in the same tree")

    # Find the common ancestor
    common_ancestor = None
    current_node = node
    while current_node:
        if current_node in target_ancestors:
            common_ancestor = current_node
            break
        current_node = current_node.parent

    if common_ancestor is None:
        # This case should ideally not happen if they are in the same tree and not the same node.
        # It implies one is an ancestor of the other, or they are in different trees (handled above).
        # If node is an ancestor of target:
        if node in target_ancestors:
            common_ancestor = node
        # If target is an ancestor of node:
        elif target in node_ancestors:
            common_ancestor = target
        else:
            raise NotInSameTreeError("Could not find common ancestor, nodes might be in different trees.")


    # Calculate path from node to common ancestor
    path_to_common = []
    current = node
    while current is not common_ancestor:
        path_to_common.append("..")
        current = current.parent
        if current is None: # Should not happen if common_ancestor is found correctly
            raise RuntimeError("Logic error in relative_path calculation")

    # Calculate path from common ancestor to target
    path_from_common = []
    current = target
    while current is not common_ancestor:
        path_from_common.append(current.name)
        current = current.parent
        if current is None: # Should not happen if common_ancestor is found correctly
            raise RuntimeError("Logic error in relative_path calculation")

    return NodePath("/".join(path_to_common + list(reversed(path_from_common))))


def resolve(node: Node, path: str | NodePath) -> Node:
    """TN-B1: supports absolute and relative NodePath values"""
    target_path = NodePath(path)

    target_path = NodePath(path)

    # Determine the starting node for resolution
    if target_path.is_absolute():
        # For absolute paths, start from the root of the tree
        current = node
        while current.parent:
            current = current.parent
    else:
        # For relative paths, start from the current node
        current = node

    # Process path segments
    segments = list(target_path.parts)

    # Skip the initial '/' for absolute paths if it's the first part
    if target_path.is_absolute() and segments and segments[0] == '/':
        segments.pop(0)

    for segment in segments:
        if segment == ".":
            # Stay at the current node
            continue
        elif segment == "..":
            # Move up to the parent
            if current.parent is None:
                raise NodeNotFoundError("Cannot resolve path above root")
            current = current.parent
        elif segment in current._children:
            # Move down to the child
            current = current._children[segment]
        else:
            # Segment not found
            raise NodeNotFoundError(f"Segment '{segment}' not found in path")

    return current


def remove(node: Node, path: str | NodePath) -> Node:
    """TN-B2: resolves a path, detaches that complete subtree, and refuses to remove the root."""
    # TN-B2: refuse to remove the root
    if node.path == NodePath("/") and NodePath(path) == NodePath("."):
        raise InvalidTreeError("Cannot remove the root node")

    target_node = resolve(node, path)
    if target_node.parent is None:
        raise InvalidTreeError("Cannot remove the root node")

    # Detach the target node and its subtree
    return detach(target_node.parent, target_node.name)


def ancestors(node: Node) -> tuple[Node, ...]:
    """TN-B4: returns ancestors in an immutable tuple."""
    if node.parent is None:
        return ()
    return (*node.parent.ancestors, node.parent)


def descendants(node: Node) -> tuple[Node, ...]:
    """TN-B4: returns descendants in depth-first pre-order."""
    nodes = []
    for child in node.children.values():
        nodes.append(child)
        nodes.extend(child.descendants)
    return tuple(nodes)


def siblings(node: Node) -> tuple[Node, ...]:
    """TN-B4: returns siblings in insertion order."""
    if node.parent is None:
        return ()
    return tuple(node.parent.children.values())


def leaves(node: Node) -> tuple[Node, ...]:
    """TN-B4: returns leaves in depth-first order."""
    nodes = []
    if not node.children:
        return (node,)
    for child in node.children.values():
        nodes.extend(child.leaves)
    return tuple(nodes)