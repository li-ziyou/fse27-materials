import pytest

from branching_tree import InvalidTreeError, Node, NodeNotFoundError


@pytest.mark.parametrize("name", ["", ".", "..", "a/b"])
def test_invalid_names_leave_both_nodes_unchanged(name):
    # TN-A1, TN-A3
    parent, child = Node.from_mapping({"keep": {}}), Node.from_mapping({"inside": {}})
    before_parent = tuple(parent.children)
    before_child = tuple(child.children)
    with pytest.raises(InvalidTreeError):
        parent.attach(name, child)
    assert tuple(parent.children) == before_parent
    assert tuple(child.children) == before_child
    assert child.parent is None and child.name is None


def test_occupied_name_and_self_link_are_atomic(form_value):
    # TN-A1, TN-A3
    occupied = form_value("occupied", "taken")
    self_name = form_value("self", "cycle")
    root = Node.from_mapping({occupied: {}})
    existing, candidate = root.resolve(occupied), Node()
    with pytest.raises(InvalidTreeError):
        root.attach(occupied, candidate)
    with pytest.raises(InvalidTreeError):
        root.attach(self_name, root)
    assert root.children == {occupied: existing}
    assert candidate.parent is None


def test_move_keeps_subtree_and_preserves_insertion_order():
    # TN-A2
    first = Node.from_mapping({"moving": {"leaf": {}}})
    second = Node.from_mapping({"before": {}})
    moving, leaf = first.resolve("moving"), first.resolve("moving/leaf")
    second.attach("after", moving)
    assert tuple(first.children) == ()
    assert tuple(second.children) == ("before", "after")
    assert moving.children["leaf"] is leaf
    assert (moving.parent, moving.name) == (second, "after")


def test_replace_with_attached_node_detaches_both_old_locations():
    # TN-A2, TN-A4
    root = Node.from_mapping({"target": {"old_leaf": {}}, "source": {"new_leaf": {}}})
    source, new_leaf = root.resolve("source"), root.resolve("source/new_leaf")
    old = root.replace("target", source)
    assert tuple(root.children) == ("target",)
    assert root.children["target"] is source and source.name == "target"
    assert source.children["new_leaf"] is new_leaf
    assert old.parent is None and old.name is None


def test_orphan_is_idempotent_and_missing_replace_is_reported():
    # TN-A4
    root = Node.from_mapping({"child": {}})
    child = root.resolve("child")
    assert child.orphan() is child
    assert child.orphan() is child
    with pytest.raises(NodeNotFoundError):
        root.replace("missing", Node())
