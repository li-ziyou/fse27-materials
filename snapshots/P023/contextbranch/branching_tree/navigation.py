from __future__ import annotations

from typing import Tuple

from .model import Node, NodeNotFoundError, NodePath, NotInSameTreeError


def resolve(node: Node, path: str | NodePath) -> Node:
    if not isinstance(path, NodePath):
        path = NodePath(path)

    current_node = node
    if path.is_absolute():
        # If the path is absolute, we need to find the root.
        root = node
        while root.parent is not None:
            root = root.parent
        current_node = root
        # For absolute paths, skip the first empty segment if it exists (e.g., from "/a/b")
        # NodePath("/a/b").parts results in ('/', 'a', 'b')
        # NodePath("a/b").parts results in ('a', 'b')
        # We need to handle the case where the first part is '/' for absolute paths
        path_segments = path.parts
        # For absolute paths, skip the first empty segment if it exists (e.g., from "/a/b")
        # NodePath("/a/b").parts results in ('/', 'a', 'b')
        # NodePath("a/b").parts results in ('a', 'b')
        # We need to handle the case where the first part is '/' for absolute paths
        path_segments = path.parts
        if path_segments and path_segments[0] == '/':
            path_segments = path_segments[1:]
        # Filter out any empty segments that might arise from paths like "//a" or "a/./b"
        path_segments = [segment for segment in path_segments if segment]
    else:
        # Filter out any empty segments for relative paths as well
        path_segments = path.parts
        path_segments = [segment for segment in path_segments if segment]

    for segment in path_segments:
        if segment == ".":
            continue
        elif segment == "..":
            if current_node.parent is None:
                raise NodeNotFoundError(f"Cannot resolve '{path}': movement above root")
            current_node = current_node.parent
        else:
            if segment not in current_node.children:
                raise NodeNotFoundError(f"Cannot resolve '{path}': segment '{segment}' not found")
            current_node = current_node.children[segment]
    return current_node


def remove(node: Node, path: str | NodePath) -> Node:
    # TN-B2: remove resolves a path, detaches that complete subtree, and refuses to remove the root.
    target_node = resolve(node, path)
    if target_node.parent is None:
        raise InvalidTreeError("Cannot remove the root node")

    # Use detach from structure.py, which should handle the actual removal and return the detached node.
    # We need to resolve the parent of the target node to call detach.
    parent_of_target = target_node.parent
    if parent_of_target is None:
        # This should not happen if target_node is not the root, but as a safeguard:
        raise NodeNotFoundError(f"Cannot remove '{path}': parent not found")

    # The name to detach is the last part of the path
    name_to_remove = NodePath(path).parts[-1]
    return parent_of_target.detach(name_to_remove)


def absolute_path(node: Node) -> NodePath:
    # TN-B3: path returns an absolute path
    if node.parent is None:
        return NodePath("/")

    path_parts = []
    current = node
    while current.parent is not None:
        if current.name is None:
            # This should not happen for a node that's part of a tree and not the root
            raise InvalidTreeError("Node has no name but is not root")
        path_parts.append(current.name)
        current = current.parent

    path_parts.reverse()
    return NodePath("/" + "/".join(path_parts))


def relative_path(node: Node, target: Node) -> NodePath:
    # TN-B3: relative_path_to returns a correct relative path for nodes in the same tree; separate trees raise NotInSameTreeError.
    if node == target:
        return NodePath(".")

    node_ancestors = node.ancestors
    target_ancestors = target.ancestors

    if node.parent is None and target.parent is None and node != target:
        raise NotInSameTreeError("Cannot find relative path between nodes in different trees (both are roots).")
    if node.parent is None and target.parent is not None:
         raise NotInSameTreeError("Cannot find relative path between root and a non-root node in different trees.")
    if node.parent is not None and target.parent is None:
         raise NotInSameTreeError("Cannot find relative path between non-root and root node in different trees.")


    # Check if they share a common root
    if node.ancestors != target.ancestors and node.resolve("/") != target.resolve("/"):
         raise NotInSameTreeError("Nodes are not in the same tree.")

    common_ancestor_level = 0
    min_len = min(len(node_ancestors), len(target_ancestors))
    for i in range(min_len):
        if node_ancestors[i] == target_ancestors[i]:
            common_ancestor_level = i + 1
        else:
            break

    # Number of steps up from 'node' to the common ancestor
    steps_up = len(node_ancestors) - common_ancestor_level
    # Path from the common ancestor down to 'target'
    # When calculating path_down, we need to use the target's absolute path
    # and make it relative to the common ancestor's path.
    common_ancestor_node = node_ancestors[common_ancestor_level - 1] if common_ancestor_level > 0 else node.resolve("/")
    path_down = target.path.relative_to(common_ancestor_node.path)

    relative_parts = [".."] * steps_up
    if path_down != NodePath("."): # If target is not the common ancestor itself
        relative_parts.extend(path_down.parts)

    return NodePath("/".join(relative_parts))


def ancestors(node: Node) -> tuple[Node, ...]:
    # TN-B4: ancestors, depth-first pre-order descendants, insertion-ordered siblings, and depth-first leaves reflect the current tree and return tuples.
    if node.parent is None:
        return ()

    ancestor_list: list[Node] = []
    current = node.parent
    while current is not None:
        ancestor_list.append(current)
        current = current.parent
    return tuple(ancestor_list)


def descendants(node: Node) -> tuple[Node, ...]:
    # TN-B4: depth-first pre-order descendants
    desc_list: list[Node] = []
    for child_name, child_node in node.children.items():
        desc_list.append(child_node)
        desc_list.extend(descendants(child_node))
    return tuple(desc_list)


def siblings(node: Node) -> tuple[Node, ...]:
    # TN-B4: insertion-ordered siblings
    if node.parent is None:
        return ()
    return tuple(n for n in node.parent.children.values() if n is not node)


def leaves(node: Node) -> tuple[Node, ...]:
    # TN-B4: depth-first leaves
    leaf_list: list[Node] = []
    if not node.children:
        leaf_list.append(node)
    else:
        for child_node in node.children.values():
            leaf_list.extend(leaves(child_node))
    return tuple(leaf_list)
