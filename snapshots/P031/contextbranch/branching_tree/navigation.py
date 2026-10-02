from __future__ import annotations

from .model import Node, NodePath, NotInSameTreeError, NodeNotFoundError, InvalidTreeError
from .structure import detach


def resolve(node: Node, path: str | NodePath) -> Node:
    if isinstance(path, str):
        path = NodePath(path)

    if isinstance(path, str):
        path = NodePath(path)

    if path.is_absolute():
        current = node
        while current.parent is not None:
            current = current.parent
        target_node = current
    else:
        target_node = node

    for segment in path.parts:
        if segment == "/":
            continue
        elif segment == ".":
            continue
        elif segment == "..":
            if target_node.parent is None:
                raise NodeNotFoundError(f"Cannot move above root: {path}")
            target_node = target_node.parent
        else:
            try:
                target_node = target_node.children[segment]
            except KeyError:
                raise NodeNotFoundError(f"Segment '{segment}' not found in path '{path}'")
    return target_node


def remove(node: Node, path: str | NodePath) -> Node:
    if path == "/" or path == "." or path == "..":
        raise NodeNotFoundError("Cannot remove root or navigate above it.")
    target_node = resolve(node, path)
    if target_node.parent is None:
        raise NodeNotFoundError("Cannot remove the root node.")
    return detach(target_node.parent, target_node.name)


def absolute_path(node: Node) -> NodePath:
    if node.parent is None:
        return NodePath("/")
    parts = []
    current = node
    while current.parent is not None:
        parts.append(current.name)
        current = current.parent
    return NodePath("/" + "/".join(reversed(parts)))


def relative_path(node: Node, target: Node) -> NodePath:
    if node is target:
        return NodePath(".")

    # Determine the root of the current node's tree
    node_root = node
    while node_root.parent is not None:
        node_root = node_root.parent

    # Determine the root of the target node's tree
    target_root = target
    while target_root.parent is not None:
        target_root = target_root.parent

    # If the roots are different, they are not in the same tree.
    if node_root is not target_root:
        raise NotInSameTreeError("Nodes are not in the same tree.")

    # Collect ancestors for both nodes
    node_ancestors = list(node.ancestors)
    target_ancestors = list(target.ancestors)

    # Find the nearest common ancestor
    common_ancestor = None
    # Iterate from the root down to find the last common ancestor
    for i in range(min(len(node_ancestors), len(target_ancestors)) - 1, -1, -1):
        if node_ancestors[i] is target_ancestors[i]:
            common_ancestor = node_ancestors[i]
            break
    
    # If no common ancestor found (and they are in the same tree), it means one is an ancestor of the other.
    # In this case, the common ancestor is the root node itself.
    if common_ancestor is None:
        if node_root is not None: # If they are in the same tree, there must be a root
             common_ancestor = node_root
        else: # Should not happen if they are in the same tree and not the same node
             raise NodeNotFoundError("Could not determine common ancestor.")

    # Path from node to common ancestor
    node_to_common = []
    current = node
    while current is not common_ancestor:
        if current.name is None: # Should not happen for nodes within a tree, except root sometimes
            raise InvalidTreeError("Node has no name, cannot construct relative path.")
        node_to_common.append(current.name)
        current = current.parent
    
    # Path from common ancestor to target
    common_to_target = []
    current = target
    while current is not common_ancestor:
        if current.name is None:
            raise InvalidTreeError("Node has no name, cannot construct relative path.")
        common_to_target.append(current.name)
        current = current.parent
    
    # Construct relative path: ".." for each step up to common ancestor, then path down to target
    path_parts = [".."] * len(node_to_common) + list(reversed(common_to_target))
    
    return NodePath("/".join(path_parts))


    # Path from node to common ancestor
    node_to_common = []
    current = node
    while current is not common_ancestor:
        node_to_common.append(current.name)
        current = current.parent
    
    # Path from common ancestor to target
    common_to_target = []
    current = target
    while current is not common_ancestor:
        common_to_target.append(current.name)
        current = current.parent
    
    # Construct relative path: ".." for each step up to common ancestor, then path down to target
    path_parts = [".."] * len(node_to_common) + list(reversed(common_to_target))
    
    return NodePath("/".join(path_parts))


def ancestors(node: Node) -> tuple[Node, ...]:
    if node.parent is None:
        return ()
    return tuple(reversed(list(node.parent.ancestors) + [node.parent]))


def descendants(node: Node) -> tuple[Node, ...]:
    all_descendants = []
    
    def traverse(current_node: Node):
        all_descendants.append(current_node)
        
        for child_name in sorted(current_node.children.keys()):
            traverse(current_node.children[child_name])

    for child_name in sorted(node.children.keys()):
        traverse(node.children[child_name])
        
    return tuple(all_descendants)


def siblings(node: Node) -> tuple[Node, ...]:
    if node.parent is None:
        return ()
    return tuple(child for child in node.parent.children.values() if child is not node)


def leaves(node: Node) -> tuple[Node, ...]:
    all_leaves = []
    nodes_to_visit = [node]
    while nodes_to_visit:
        current = nodes_to_visit.pop(0)
        if not current.children:
            all_leaves.append(current)
        else:
            nodes_to_visit.extend(current.children.values())
    return tuple(all_leaves)
