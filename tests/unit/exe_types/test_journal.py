"""Recording writes to journaled containers and attributes, and reversing them."""

import copy

import pytest

from griptape_nodes.exe_types import journal
from griptape_nodes.exe_types.journal import JournaledDict, JournaledList, Transaction


class _Thing:
    flag = False
    name: str

    def __setattr__(self, name: str, value: object) -> None:
        journal.record_attribute(self, name, value)
        super().__setattr__(name, value)


def _record(write: object) -> Transaction:
    transaction = Transaction()
    with journal.recording(transaction):
        write()  # type: ignore[operator]
    return transaction


class TestJournaledDict:
    def test_undo_and_redo_every_kind_of_write(self) -> None:
        data = JournaledDict({"a": 1, "b": 2, "c": 3})

        def write() -> None:
            data["a"] = 10
            del data["b"]
            data.pop("c")
            data.update(d=4)
            data.setdefault("e", 5)

        transaction = _record(write)
        assert data == {"a": 10, "d": 4, "e": 5}

        transaction.undo()
        assert data == {"a": 1, "b": 2, "c": 3}
        transaction.redo()
        assert data == {"a": 10, "d": 4, "e": 5}

    def test_deep_records_writes_to_nested_containers(self) -> None:
        metadata = JournaledDict({"position": {"x": 0}}, aspect=journal.Aspect.METADATA, deep=True)
        transaction = _record(lambda: metadata["position"].__setitem__("x", 5))

        transaction.undo()

        assert metadata["position"] == {"x": 0}
        assert metadata["position"].aspect is journal.Aspect.METADATA
        assert metadata["position"].root_key == "position"

    def test_writes_outside_a_transaction_are_not_recorded(self) -> None:
        data = JournaledDict()
        data["a"] = 1
        assert journal.active() is None

    def test_copies_and_pickles_are_plain(self) -> None:
        data = JournaledDict({"nested": {"x": 1}}, deep=True)

        for result in (copy.copy(data), copy.deepcopy(data)):
            assert type(result) is dict
        assert type(copy.deepcopy(data)["nested"]) is dict


class TestJournaledList:
    def test_undo_and_redo_every_kind_of_write(self) -> None:
        items = JournaledList([1, 2, 3])

        def write() -> None:
            items.append(4)
            items.remove(1)
            items.insert(0, 0)
            items[1] = 20
            items.pop()

        transaction = _record(write)
        assert items == [0, 20, 3]

        transaction.undo()
        assert items == [1, 2, 3]
        transaction.redo()
        assert items == [0, 20, 3]

    def test_undo_removes_the_inserted_item_even_after_other_inserts(self) -> None:
        a, b = object(), object()
        items = JournaledList()
        transaction = _record(lambda: items.append(a))
        items.insert(0, b)

        transaction.undo()

        assert items == [b]


class TestAttributes:
    def test_first_assignment_is_not_recorded(self) -> None:
        thing = _Thing()
        transaction = _record(lambda: setattr(thing, "name", "x"))

        assert transaction.changes == []

    def test_overwrite_and_class_default_are_recorded(self) -> None:
        thing = _Thing()
        thing.name = "x"

        def write() -> None:
            thing.name = "y"
            thing.flag = True

        transaction = _record(write)
        transaction.undo()

        assert thing.name == "x"
        assert "flag" not in thing.__dict__
        assert thing.flag is False


class TestConflicts:
    def test_a_third_state_conflicts_and_rolls_back_what_was_undone(self) -> None:
        data = JournaledDict({"a": 1, "b": 1})

        def write() -> None:
            data["a"] = 2
            data["b"] = 2

        transaction = _record(write)
        data["a"] = 3

        with pytest.raises(journal.Conflict):
            transaction.undo()
        assert data == {"a": 3, "b": 2}

    def test_apply_records_the_change_but_not_its_own_writes(self) -> None:
        data = JournaledDict({"a": 1})

        class _Set(journal.Structural):
            def make(self) -> None:
                data["a"] = 2

            def unmake(self) -> None:
                data["a"] = 1

            def needed(self, *, undoing: bool) -> bool:
                return data["a"] == (2 if undoing else 1)

        change = _Set()
        transaction = _record(lambda: journal.apply(change))

        assert data == {"a": 2}
        assert transaction.changes == [change]
        transaction.undo()
        assert data == {"a": 1}

    def test_undo_skips_a_place_already_where_it_leads(self) -> None:
        data = JournaledDict({"a": 1})
        transaction = _record(lambda: data.__setitem__("a", 2))
        data["a"] = 1

        assert transaction.undo() == []
        assert data == {"a": 1}
