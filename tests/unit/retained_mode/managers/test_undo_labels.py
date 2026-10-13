"""Labels for history entries."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest

from griptape_nodes.retained_mode.managers.undo.history import (
    HistoryEntry,
    NodeChange,
    _count,
    describe,
    describe_changes,
)
from griptape_nodes.retained_mode.managers.undo.snapshot import ConnectionKey, NodeImage

_BASE = NodeImage(
    name="A",
    node_type="_Probe",
    flow_name="main",
    parent_group=None,
    is_group=False,
    members=(),
    metadata={"position": {"x": 0, "y": 0}},
    lock=False,
    parameters=("text",),
    values={},
    explicit_values=frozenset(),
    structure="s",
    connections=frozenset(),
    commands=None,  # type: ignore[arg-type]
    value_commands=[],
    value_pool={},
)


def _image(**overrides: Any) -> NodeImage:
    return replace(_BASE, **overrides)


def _modified(before: NodeImage, after: NodeImage, **entry: Any) -> HistoryEntry:
    return HistoryEntry(changes=[NodeChange(before=before, after=after)], **entry)


def _key(source: str, target: str) -> ConnectionKey:
    return ConnectionKey(source_node=source, source_parameter="text", target_node=target, target_parameter="text")


class _Unequal:
    def __eq__(self, other: object) -> bool:
        msg = "cannot compare"
        raise TypeError(msg)

    __hash__ = object.__hash__


class TestDescribe:
    def test_recreating_nodes_under_the_same_names_is_a_reset(self) -> None:
        entry = HistoryEntry(changes=[NodeChange(before=_image(), after=None), NodeChange(before=None, after=_image())])

        assert describe(entry) == "Reset 'A'"

    def test_adding_and_deleting_different_nodes_is_an_edit(self) -> None:
        entry = HistoryEntry(
            changes=[
                NodeChange(before=_image(name="A"), after=None),
                NodeChange(before=None, after=_image(name="B")),
                NodeChange(before=_image(name="C"), after=_image(name="C", lock=True)),
            ]
        )

        assert describe(entry) == "Edit 3 nodes"

    def test_several_deletes(self) -> None:
        entry = HistoryEntry(
            changes=[NodeChange(before=_image(name="A"), after=None), NodeChange(before=_image(name="B"), after=None)]
        )

        assert describe(entry) == "Delete 2 nodes"

    def test_several_renames(self) -> None:
        entry = HistoryEntry(
            changes=[
                NodeChange(before=_image(name="A"), after=_image(name="X")),
                NodeChange(before=_image(name="B"), after=_image(name="Y")),
            ]
        )

        assert describe(entry) == "Rename 2 nodes"

    def test_grouping(self) -> None:
        assert describe(_modified(_image(), _image(parent_group="G"))) == "Group 'A'"
        assert describe(_modified(_image(parent_group="G"), _image())) == "Ungroup 'A'"

    def test_a_new_connection_outranks_the_value_it_set(self) -> None:
        entry = _modified(_image(), _image(values={"text": "v"}), connections_added=frozenset({_key("B", "A")}))

        assert describe(entry) == "Connect 'B' to 'A'"

    @pytest.mark.parametrize(
        ("added", "removed", "label"),
        [
            ({_key("A", "B")}, set(), "Connect 'A' to 'B'"),
            (set(), {_key("A", "B")}, "Disconnect 'A' from 'B'"),
            ({_key("A", "B"), _key("A", "C")}, set(), "Add 2 connections"),
            (set(), {_key("A", "B"), _key("A", "C")}, "Remove 2 connections"),
            ({_key("A", "B")}, {_key("A", "C")}, "Change connections"),
        ],
    )
    def test_connections(self, added: set[ConnectionKey], removed: set[ConnectionKey], label: str) -> None:
        entry = HistoryEntry(connections_added=frozenset(added), connections_removed=frozenset(removed))

        assert describe(entry) == label

    @pytest.mark.parametrize(
        ("parameters", "label"),
        [
            (("text", "extra"), "Add 'extra' to 'A'"),
            ((), "Remove 'text' from 'A'"),
            (("other",), "Edit parameters on 'A'"),
        ],
    )
    def test_parameter_set(self, parameters: tuple[str, ...], label: str) -> None:
        assert describe(_modified(_image(), _image(parameters=parameters, structure="t"))) == label

    def test_several_values(self) -> None:
        after = _image(values={"text": "1", "other": "2"})

        assert describe(_modified(_image(), after)) == "Change 2 values on 'A'"

    def test_structure_alone(self) -> None:
        assert describe(_modified(_image(), _image(structure="t"))) == "Edit parameters on 'A'"

    def test_locks(self) -> None:
        assert describe(_modified(_image(), _image(lock=True))) == "Lock 'A'"
        assert describe(_modified(_image(lock=True), _image())) == "Unlock 'A'"

    def test_a_lock_with_a_metadata_change_is_not_called_a_lock(self) -> None:
        after = _image(lock=True, metadata={"position": {"x": 1, "y": 1}})

        assert describe(_modified(_image(), after)) == "Move 'A'"

    def test_layout(self) -> None:
        moved = _image(metadata={"position": {"x": 1, "y": 1}})
        resized = _image(metadata={"position": {"x": 0, "y": 0}, "size": {"width": 1, "height": 1}})

        assert describe(_modified(_image(), moved)) == "Move 'A'"
        assert describe(_modified(_image(), resized)) == "Resize 'A'"

    def test_other_metadata_falls_back_to_edit(self) -> None:
        after = _image(metadata={"position": {"x": 0, "y": 0}, "collapsed": True})

        assert describe(_modified(_image(), after)) == "Edit 'A'"

    def test_describe_changes_lists_each_change(self) -> None:
        entry = HistoryEntry(
            changes=[
                NodeChange(before=None, after=_image(name="New")),
                NodeChange(before=_image(name="Old"), after=None),
                NodeChange(before=_image(), after=_image(values={"text": "v"}, structure="t")),
            ],
            connections_added=frozenset({_key("A", "B")}),
            connections_removed=frozenset({_key("C", "D")}),
        )

        assert describe_changes(entry) == (
            "added New; deleted Old; A [text, <parameters>]; connected A.text; disconnected C.text"
        )

    def test_describe_changes_skips_a_node_missing_on_both_sides(self) -> None:
        assert describe_changes(HistoryEntry(changes=[NodeChange(before=None, after=None)])) == ""

    def test_count(self) -> None:
        assert _count(1, "node") == "1 node"
        assert _count(2, "node") == "2 nodes"


class TestNodeImage:
    def test_metadata_that_cannot_be_compared_counts_as_changed(self) -> None:
        before = _image(metadata={"thing": _Unequal()})
        after = _image(metadata={"thing": _Unequal()})

        assert before.changed_metadata_keys(after) == {"thing"}
        assert not before.same_state(after)
