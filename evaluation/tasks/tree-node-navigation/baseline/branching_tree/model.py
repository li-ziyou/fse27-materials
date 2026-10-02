from __future__ import annotations

from collections.abc import Mapping
from pathlib import PurePosixPath
from types import MappingProxyType
from typing import Self


class InvalidTreeError(ValueError):
    """The requested structural change would make the tree invalid."""


class NodeNotFoundError(KeyError):
    """A path cannot be resolved in the current tree."""


class NotInSameTreeError(ValueError):
    """A relative path was requested between separate trees."""


class NodePath(PurePosixPath):
    """An absolute or relative path between tree nodes."""


class Node:
    def __init__(self) -> None:
        self._parent: Node | None = None
        self._name: str | None = None
        self._children: dict[str, Node] = {}

    @classmethod
    def from_mapping(cls, tree: Mapping[str, dict]) -> Self:
        root = cls()

        def populate(parent: Node, values: Mapping[str, dict]) -> None:
            for name, descendants in values.items():
                child = cls()
                child._parent = parent
                child._name = name
                parent._children[name] = child
                populate(child, descendants)

        populate(root, tree)
        return root

    @property
    def name(self) -> str | None:
        return self._name

    @property
    def parent(self) -> Node | None:
        return self._parent

    @property
    def children(self) -> Mapping[str, Node]:
        return MappingProxyType(self._children)

    def attach(self, name: str, child: Node) -> None:
        from .structure import attach

        attach(self, name, child)

    def detach(self, name: str) -> Node:
        from .structure import detach

        return detach(self, name)

    def replace(self, name: str, child: Node) -> Node:
        from .structure import replace

        return replace(self, name, child)

    def orphan(self) -> Node:
        from .structure import orphan

        return orphan(self)

    def resolve(self, path: str | NodePath) -> Node:
        from .navigation import resolve

        return resolve(self, path)

    def remove(self, path: str | NodePath) -> Node:
        from .navigation import remove

        return remove(self, path)

    @property
    def path(self) -> NodePath:
        from .navigation import absolute_path

        return absolute_path(self)

    def relative_path_to(self, target: Node) -> NodePath:
        from .navigation import relative_path

        return relative_path(self, target)

    @property
    def ancestors(self) -> tuple[Node, ...]:
        from .navigation import ancestors

        return ancestors(self)

    @property
    def descendants(self) -> tuple[Node, ...]:
        from .navigation import descendants

        return descendants(self)

    @property
    def siblings(self) -> tuple[Node, ...]:
        from .navigation import siblings

        return siblings(self)

    @property
    def leaves(self) -> tuple[Node, ...]:
        from .navigation import leaves

        return leaves(self)
