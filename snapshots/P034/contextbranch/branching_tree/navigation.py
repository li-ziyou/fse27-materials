from __future__ import annotations

from .model import Node, NodePath


def resolve(node: Node, path: str | NodePath) -> Node:
    from .model import NodeNotFoundError
    
    path_obj = NodePath(path)
    current = node
    
    # Absolute paths start from root
    if path_obj.is_absolute():
        current = node
        while current.parent is not None:
            current = current.parent
        parts = path_obj.parts[1:]  # Skip the leading '/'
    else:
        parts = path_obj.parts
    
    # Navigate through each part
    for part in parts:
        if part == '.':
            continue
        elif part == '..':
            if current.parent is None:
                raise NodeNotFoundError(f"Cannot go above root")
            current = current.parent
        else:
            if part not in current.children:
                raise NodeNotFoundError(f"Path segment '{part}' not found")
            current = current.children[part]
    
    return current


def remove(node: Node, path: str | NodePath) -> Node:
    from .model import InvalidTreeError, NodeNotFoundError
    
    target = resolve(node, path)
    
    # Cannot remove root
    if target.parent is None:
        raise InvalidTreeError("Cannot remove the root node")
    
    return target.orphan()


def absolute_path(node: Node) -> NodePath:
    parts = []
    current = node
    
    while current.parent is not None:
        parts.append(current.name)
        current = current.parent
    
    parts.reverse()
    return NodePath('/' + '/'.join(parts)) if parts else NodePath('/')


def relative_path(node: Node, target: Node) -> NodePath:
    from .model import NotInSameTreeError
    
    # Find roots of both nodes
    node_root = node
    while node_root.parent is not None:
        node_root = node_root.parent
    
    target_root = target
    while target_root.parent is not None:
        target_root = target_root.parent
    
    if node_root is not target_root:
        raise NotInSameTreeError("Nodes are not in the same tree")
    
    # Get absolute paths
    node_path = absolute_path(node)
    target_path = absolute_path(target)
    
    node_parts = node_path.parts[1:]  # Skip leading '/'
    target_parts = target_path.parts[1:]  # Skip leading '/'
    
    # Find common ancestor
    common_idx = 0
    for i, (np, tp) in enumerate(zip(node_parts, target_parts)):
        if np == tp:
            common_idx = i + 1
        else:
            break
    
    # Build relative path: go up from node to common ancestor, then down to target
    ups = len(node_parts) - common_idx
    downs = target_parts[common_idx:]
    
    parts = ['..'] * ups + list(downs)
    return NodePath('/'.join(parts)) if parts else NodePath('.')


def ancestors(node: Node) -> tuple[Node, ...]:
    result = []
    current = node.parent
    
    while current is not None:
        result.append(current)
        current = current.parent
    
    return tuple(result)


def descendants(node: Node) -> tuple[Node, ...]:
    result = []
    
    def dfs_preorder(n: Node) -> None:
        for child in n.children.values():
            result.append(child)
            dfs_preorder(child)
    
    dfs_preorder(node)
    return tuple(result)


def siblings(node: Node) -> tuple[Node, ...]:
    if node.parent is None:
        return ()
    
    result = []
    for name, child in node.parent.children.items():
        if child is not node:
            result.append(child)
    
    return tuple(result)


def leaves(node: Node) -> tuple[Node, ...]:
    result = []
    
    def dfs(n: Node) -> None:
        if not n.children:
            result.append(n)
        else:
            for child in n.children.values():
                dfs(child)
    
    dfs(node)
    return tuple(result)
