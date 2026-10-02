from __future__ import annotations

from .model import Node, NodePath


def resolve(node: Node, path: str | NodePath) -> Node:
    raise NotImplementedError


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
