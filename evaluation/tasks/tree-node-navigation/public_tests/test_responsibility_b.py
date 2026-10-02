import pytest

from branching_tree import Node, NodeNotFoundError, NodePath, NotInSameTreeError


def sample_tree():
    return Node.from_mapping({"a": {"x": {}, "y": {}}, "b": {"z": {}}})


def test_resolves_absolute_relative_and_parent_paths(form_value):
    # TN-B1, TN-B3
    first = form_value("a", "left")
    x_name = form_value("x", "first")
    y_name = form_value("y", "second")
    second = form_value("b", "right")
    z_name = form_value("z", "leaf")
    root = Node.from_mapping({first: {x_name: {}, y_name: {}}, second: {z_name: {}}})
    x = root.resolve(NodePath(f"/{first}/{x_name}"))
    assert x.resolve(f"../{y_name}") is root.resolve(f"/{first}/{y_name}")
    assert x.path == NodePath(f"/{first}/{x_name}")
    assert x.relative_path_to(root.resolve(f"{second}/{z_name}")) == NodePath(f"../../{second}/{z_name}")


def test_traversal_views_have_the_disclosed_order():
    # TN-B4
    root = sample_tree()
    a, x, y, b, z = (root.resolve(path) for path in ("a", "a/x", "a/y", "b", "b/z"))
    assert root.descendants == (a, x, y, b, z)
    assert x.ancestors == (a, root)
    assert x.siblings == (y,)
    assert root.leaves == (x, y, z)


def test_navigation_errors_are_explicit():
    # TN-B1, TN-B3
    root = sample_tree()
    with pytest.raises(NodeNotFoundError):
        root.resolve("../outside")
    with pytest.raises(NotInSameTreeError):
        root.relative_path_to(Node())
