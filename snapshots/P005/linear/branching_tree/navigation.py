from __future__ import annotations

from .model import Node, NodePath, InvalidTreeError, NodeNotFoundError


def resolve(node: Node, path: str | NodePath) -> Node:
    if not isinstance(path, NodePath):
        path = NodePath(path)

    # If the path is absolute, start from the root.
    if path.is_absolute():
        current_node = node
        while current_node.parent is not None:
            current_node = current_node.parent
        # Now current_node is the root
    else:
        current_node = node

    for segment in path.parts:
        if segment == ".":
            continue
        elif segment == "..":
            if current_node.parent is None:
                # Cannot go above the root
                raise NodeNotFoundError(f"Path '{path}' goes above the root.")
            current_node = current_node.parent
        else:
            if segment not in current_node.children:
                raise NodeNotFoundError(f"Path segment '{segment}' not found in '{path}'.")
            current_node = current_node.children[segment]

    return current_node


def remove(node: Node, path: str | NodePath) -> Node:
    raise NotImplementedError


def absolute_path(node: Node) -> NodePath:
    raise NotImplementedError


def relative_path(node: Node, target: Node) -> NodePath:
    raise NotImplementedError


def ancestors(node: Node) -> tuple[Node, ...]:
    raise NotImplementedError


def descendants(node: Node) -> tuple[Node, ...]:
    raise NotImplementedError


def siblings(node: Node) -> tuple[Node, ...]:
    raise NotImplementedError


def leaves(node: Node) -> tuple[Node, ...]:
    raise NotImplementedError
