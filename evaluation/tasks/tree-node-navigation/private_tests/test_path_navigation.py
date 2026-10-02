import pytest

from branching_tree import Node, NodeNotFoundError, NodePath, NotInSameTreeError


def tree():
    return Node.from_mapping({"one": {"a": {}, "b": {"deep": {}}}, "two": {"c": {}}})


@pytest.mark.parametrize("path", ["missing", "one/missing", "/two/c/missing", "../../outside"])
def test_missing_paths_raise_the_contract_error(path):
    # TN-B1
    with pytest.raises(NodeNotFoundError):
        tree().resolve(path)


def test_dot_absolute_root_and_parent_resolution():
    # TN-B1
    root = tree()
    deep = root.resolve("one/b/deep")
    assert deep.resolve(".") is deep
    assert deep.resolve("../..") is root.resolve("one")
    assert deep.resolve(NodePath("/")) is root


def test_absolute_and_relative_paths_cover_self_ancestor_and_cousin(form_value):
    # TN-B3
    first = form_value("one", "source")
    branch = form_value("b", "branch")
    deep_name = form_value("deep", "tip")
    second = form_value("two", "target")
    cousin = form_value("c", "cousin")
    root = Node.from_mapping({first: {branch: {deep_name: {}}}, second: {cousin: {}}})
    deep, one, c = root.resolve(f"{first}/{branch}/{deep_name}"), root.resolve(first), root.resolve(f"{second}/{cousin}")
    assert deep.path == NodePath(f"/{first}/{branch}/{deep_name}")
    assert deep.relative_path_to(deep) == NodePath(".")
    assert deep.relative_path_to(one) == NodePath("../..")
    assert deep.relative_path_to(c) == NodePath(f"../../../{second}/{cousin}")
    with pytest.raises(NotInSameTreeError):
        c.relative_path_to(Node())


def test_traversals_are_dynamic_tuples_in_disclosed_order():
    # TN-B4
    root = tree()
    one, a, b, deep, two, c = (root.resolve(path) for path in ("one", "one/a", "one/b", "one/b/deep", "two", "two/c"))
    assert root.descendants == (one, a, b, deep, two, c)
    assert deep.ancestors == (b, one, root)
    assert b.siblings == (a,)
    assert root.leaves == (a, deep, c)
    assert deep.leaves == (deep,)


def test_remove_refuses_root():
    # TN-B2
    root = tree()
    with pytest.raises(NodeNotFoundError):
        root.remove("/")
    assert tuple(root.children) == ("one", "two")
