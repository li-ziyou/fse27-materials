from __future__ import annotations

from .model import Node, NodePath, NodeNotFoundError, InvalidTreeError, NotInSameTreeError


def resolve(node: Node, path: str | NodePath) -> Node:
    if isinstance(path, str):
        path = NodePath(path)

    if path.is_absolute():
        root = node
        while root.parent is not None:
            root = root.parent
        current = root
        # Skip the leading '/' part for absolute paths
        parts_to_iterate = path.parts[1:]
    else:
        current = node
        parts_to_iterate = path.parts

    for part in parts_to_iterate:
        if part == ".":
            continue
        elif part == "..":
            if current.parent is None:
                raise NodeNotFoundError("Cannot resolve path above root")
            current = current.parent
        else:
            if part not in current._children:
                raise NodeNotFoundError(f"Path segment '{part}' not found")
            current = current._children[part]
    return current


def remove(node: Node, path: str | NodePath) -> Node:
    target_node = resolve(node, path)
    if target_node.parent is None:
        raise InvalidTreeError("Cannot remove the root node")
    return target_node.parent.detach(target_node.name)


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
    if node.parent is None and target.parent is None:
        if node is target:
            return NodePath(".")
        else:
            raise NotInSameTreeError("Nodes are in different trees")

    node_root = node
    while node_root.parent is not None:
        node_root = node_root.parent

    target_root = target
    while target_root.parent is not None:
        target_root = target_root.parent

    if node_root is not target_root:
        raise NotInSameTreeError("Nodes are in different trees")

    node_path_parts = absolute_path(node).parts
    target_path_parts = absolute_path(target).parts

    lca_depth = 0
    while lca_depth < len(node_path_parts) and lca_depth < len(target_path_parts) and \
          node_path_parts[lca_depth] == target_path_parts[lca_depth]:
        lca_depth += 1

    relative_parts = [".."] * (len(node_path_parts) - lca_depth)
    relative_parts.extend(target_path_parts[lca_depth:])

    return NodePath("/".join(relative_parts))


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
    descendants_list = []
    
    def _traverse(current_node):
        for child in current_node._children.values():
            descendants_list.append(child)
            _traverse(child)

    _traverse(node)
    return tuple(descendants_list)


def siblings(node: Node) -> tuple[Node, ...]:
    if node.parent is None:
        return ()
    
    sibling_list = []
    for name, child in node.parent._children.items():
        if child is not node:
            sibling_list.append(child)
    return tuple(sibling_list)


def leaves(node: Node) -> tuple[Node, ...]:
    leaves_list = []
    
    def _traverse(current_node):
        if not current_node._children:
            leaves_list.append(current_node)
            return
        
        for child in current_node._children.values():
            _traverse(child)

    _traverse(node)
    return tuple(leaves_list)
