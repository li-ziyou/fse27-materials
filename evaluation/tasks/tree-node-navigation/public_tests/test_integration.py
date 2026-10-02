import pytest

from branching_tree import InvalidTreeError, Node, NodeNotFoundError, NodePath


def test_moving_subtree_immediately_changes_paths_but_keeps_contents(form_value):
    # TN-I1, TN-A2, TN-B1, TN-B3
    source = form_value("left", "source")
    target = form_value("right", "target")
    moved = form_value("moved", "relocated")
    leaf_name = form_value("leaf", "tip")
    root = Node.from_mapping({source: {leaf_name: {}}, target: {}})
    leaf = root.resolve(f"{source}/{leaf_name}")
    root.resolve(target).attach(moved, root.resolve(source))
    assert leaf.path == NodePath(f"/{target}/{moved}/{leaf_name}")
    assert root.resolve(leaf.path) is leaf
    with pytest.raises(NodeNotFoundError):
        root.resolve(f"{source}/{leaf_name}")


def test_path_removal_detaches_the_complete_subtree():
    # TN-I1, TN-A4, TN-B2
    root = Node.from_mapping({"keep": {}, "drop": {"leaf": {}}})
    removed = root.remove("drop")
    assert removed.parent is None and removed.resolve("leaf").path == NodePath("/leaf")
    assert tuple(root.children) == ("keep",)


def test_rejected_cycle_preserves_navigation_results():
    # TN-I1, TN-A3, TN-B3
    root = Node.from_mapping({"a": {"b": {}}})
    before = tuple(node.path for node in (root, *root.descendants))
    with pytest.raises(InvalidTreeError):
        root.resolve("a/b").attach("bad", root)
    assert tuple(node.path for node in (root, *root.descendants)) == before
