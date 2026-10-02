from __future__ import annotations

from .model import Node


def attach(parent: Node, name: str, child: Node) -> None:
    raise NotImplementedError


def detach(parent: Node, name: str) -> Node:
    raise NotImplementedError


def replace(parent: Node, name: str, child: Node) -> Node:
    raise NotImplementedError


def orphan(node: Node) -> Node:
    raise NotImplementedError
