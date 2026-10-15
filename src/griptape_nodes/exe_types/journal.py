"""A record of changes to workflow state, so a user action can be reversed and re-applied.

A transaction holds one user action's changes, in order. There are two kinds. Structural changes,
such as a node added or a connection removed, are records the managers make through `apply`: the
record carries out the change, so making it and redoing it are the same code. The records are in
`changes.py`, and `test_structural_ownership.py` checks that nothing changes structure without one.
Changes inside a node, its values, metadata, and element tree, are written by library code directly,
so the containers that hold them, and the element `__setattr__` hook, record each write themselves.

Writes outside a transaction are not recorded: running a workflow, loading one, or the engine's own
bookkeeping. Inside one, an element field's first assignment is skipped, since no one could have
seen the element without it, unless the class provides a default the element was reading.
"""

from __future__ import annotations

import copy
import logging
from abc import ABC, abstractmethod
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass
from enum import StrEnum, auto
from typing import TYPE_CHECKING, Any, Self, SupportsIndex

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator

logger = logging.getLogger("griptape_nodes")

STALE = "the workflow has changed since in a way that step cannot be applied over."


class _Missing:
    def __repr__(self) -> str:
        return "MISSING"


MISSING: Any = _Missing()


class Aspect(StrEnum):
    """Which part of a node or flow a journaled container holds."""

    FLOW_METADATA = auto()
    VALUES = auto()
    METADATA = auto()
    GROUP_PROXIES = auto()
    CHILDREN = auto()
    ADDED_PARAMETERS = auto()


class Conflict(Exception):  # noqa: N818
    """A change cannot be reversed or re-applied over what the workflow holds now."""


class Change(ABC):
    """One step of an edit, able to reverse and re-apply itself.

    Each method returns False when the workflow is already where it would lead, so it was skipped,
    and raises Conflict when something outside the history has moved it somewhere else.
    """

    @abstractmethod
    def undo(self) -> bool: ...

    @abstractmethod
    def redo(self) -> bool: ...


class Structural(Change):
    """A change a manager makes through `apply`, by calling one of its own methods.

    Making it does not check the workflow, since the handler making it already validated the edit.
    Undo and redo check first, since other edits may have happened in between.
    """

    __slots__ = ()

    @abstractmethod
    def make(self) -> None: ...

    @abstractmethod
    def unmake(self) -> None: ...

    @abstractmethod
    def needed(self, *, undoing: bool) -> bool:
        """Whether undoing or redoing has anything to do. Raises Conflict if it cannot be done."""

    def undo(self) -> bool:
        if not self.needed(undoing=True):
            return False
        self.unmake()
        return True

    def redo(self) -> bool:
        if not self.needed(undoing=False):
            return False
        self.make()
        return True


@dataclass(frozen=True, slots=True)
class SetItem(Change):
    """A dict key set or removed. MISSING on either side means the key was absent."""

    target: dict
    key: Any
    old: Any
    new: Any

    def undo(self) -> bool:
        return _move_item(self.target, self.key, self.new, self.old)

    def redo(self) -> bool:
        return _move_item(self.target, self.key, self.old, self.new)


@dataclass(frozen=True, slots=True)
class SetAttribute(Change):
    target: object
    name: str
    old: Any
    new: Any

    def undo(self) -> bool:
        return _move_attribute(self.target, self.name, self.new, self.old)

    def redo(self) -> bool:
        return _move_attribute(self.target, self.name, self.old, self.new)


@dataclass(frozen=True, slots=True)
class InsertItem(Change):
    """An item added to a list.

    Items are found by identity when reversed, so writes from other edits in between do not shift
    which item is removed.
    """

    target: list
    index: int
    item: Any

    def undo(self) -> bool:
        return _remove_from_list(self.target, self.index, self.item)

    def redo(self) -> bool:
        return _insert_into_list(self.target, self.index, self.item)


@dataclass(frozen=True, slots=True)
class RemoveItem(Change):
    target: list
    index: int
    item: Any

    def undo(self) -> bool:
        return _insert_into_list(self.target, self.index, self.item)

    def redo(self) -> bool:
        return _remove_from_list(self.target, self.index, self.item)


class Transaction:
    """The changes of one user action, in the order they were made."""

    def __init__(self) -> None:
        self.changes: list[Change] = []
        # Closed while none of the action's requests is running, so a task a handler left behind
        # cannot add to an action that is already done.
        self.accepting = True

    def record(self, change: Change) -> None:
        if self.accepting:
            self.changes.append(change)

    def undo(self) -> list[str]:
        """Reverse every change, newest first. Returns a sentence for each that failed.

        Raises:
            Conflict: A change cannot be reversed. The ones already reversed are re-applied, so the
                workflow is left as it was.
        """
        return _replay(list(reversed(self.changes)), undoing=True)

    def redo(self) -> list[str]:
        return _replay(self.changes, undoing=False)


_active: ContextVar[Transaction | None] = ContextVar("journal_active_transaction", default=None)


def active() -> Transaction | None:
    """The transaction writes in this context go to, if any."""
    return _active.get()


def begin(transaction: Transaction | None) -> Token[Transaction | None]:
    """Record writes made in this context, and in tasks it starts, into `transaction`, or nowhere."""
    return _active.set(transaction)


def end(token: Token[Transaction | None]) -> None:
    """Go back to recording wherever this context recorded before `begin`."""
    _active.reset(token)


@contextmanager
def recording(transaction: Transaction | None) -> Iterator[None]:
    """Record into `transaction`, or nowhere, for the duration of the block."""
    token = begin(transaction)
    try:
        yield
    finally:
        end(token)


def apply(change: Structural) -> None:
    """Make a structural change and record it.

    The change carries itself out, so what it writes is its own and is not recorded separately.
    """
    with recording(None):
        change.make()
    _record(change)


def record_attribute(target: object, name: str, value: Any) -> None:
    """Record an attribute assignment that is about to happen."""
    transaction = _active.get()
    if transaction is None:
        return
    default = getattr(type(target), name, MISSING)
    # A property stores the value somewhere else, and that write is recorded on its own.
    if hasattr(default, "__set__"):
        return
    old = target.__dict__.get(name, MISSING)
    if old is value:
        return
    # A class default is state the object had before this first assignment.
    if old is MISSING and default is MISSING:
        return
    transaction.record(SetAttribute(target=target, name=name, old=old, new=value))


class JournaledDict(dict):
    """A dict whose writes are recorded.

    Args:
        owner: The object this dict holds state for, such as a node. Used to report what changed.
        aspect: Which part of the workflow this is.
        deep: Also record writes to the plain dicts and lists stored in it, at any depth.
        root_key: For a container nested inside another, the top-level key it sits under, such as
            "position" in a node's metadata. MISSING for a top-level container.
    """

    def __init__(
        self,
        data: Any = (),
        *,
        owner: object = None,
        aspect: Aspect | None = None,
        deep: bool = False,
        root_key: Any = MISSING,
        **kwargs: Any,
    ) -> None:
        super().__init__()
        self.owner = owner
        self.aspect = aspect
        self.deep = deep
        self.root_key = root_key
        for key, value in dict(data, **kwargs).items():
            dict.__setitem__(self, key, self._adopt(key, value))

    def __setitem__(self, key: Any, value: Any) -> None:
        value = self._adopt(key, value)
        old = dict.get(self, key, MISSING)
        dict.__setitem__(self, key, value)
        _record(SetItem(target=self, key=key, old=old, new=value))

    def __delitem__(self, key: Any) -> None:
        old = dict.__getitem__(self, key)
        dict.__delitem__(self, key)
        _record(SetItem(target=self, key=key, old=old, new=MISSING))

    def __ior__(self, other: Any) -> Self:  # type: ignore[override]
        self.update(other)
        return self

    def __reduce__(self) -> tuple[Any, ...]:
        # Copies and pickles are plain data, not part of the workflow.
        return (dict, (dict(self),))

    def __copy__(self) -> dict:
        return dict(self)

    def __deepcopy__(self, memo: dict[int, Any]) -> dict:
        return copy.deepcopy(dict(self), memo)

    def pop(self, key: Any, *default: Any) -> Any:
        if key in self:
            value = dict.__getitem__(self, key)
            del self[key]
            return value
        if default:
            return default[0]
        raise KeyError(key)

    def popitem(self) -> tuple[Any, Any]:
        key, value = dict.popitem(self)
        _record(SetItem(target=self, key=key, old=value, new=MISSING))
        return key, value

    def setdefault(self, key: Any, default: Any = None) -> Any:
        if key not in self:
            self[key] = default
        return dict.__getitem__(self, key)

    def update(self, *args: Any, **kwargs: Any) -> None:
        for key, value in dict(*args, **kwargs).items():
            self[key] = value

    def clear(self) -> None:
        for key in list(self):
            del self[key]

    def _adopt(self, key: Any, value: Any) -> Any:
        if not self.deep:
            return value
        root_key = key if self.root_key is MISSING else self.root_key
        return _adopt_nested(value, owner=self.owner, aspect=self.aspect, root_key=root_key)


class JournaledList(list):
    """A list whose writes are recorded. See JournaledDict for the arguments."""

    def __init__(
        self,
        data: Iterable[Any] = (),
        *,
        owner: object = None,
        aspect: Aspect | None = None,
        deep: bool = False,
        root_key: Any = MISSING,
    ) -> None:
        super().__init__()
        self.owner = owner
        self.aspect = aspect
        self.deep = deep
        self.root_key = root_key
        list.extend(self, (self._adopt(item) for item in data))

    def __setitem__(self, index: Any, value: Any) -> None:
        if isinstance(index, slice):
            start = index.indices(len(self))[0]
            del self[index]
            for offset, item in enumerate(list(value)):
                self.insert(start + offset, item)
            return
        position = _position(self, index)
        del self[position]
        self.insert(position, value)

    def __delitem__(self, index: Any) -> None:
        if isinstance(index, slice):
            for position in sorted(range(*index.indices(len(self))), reverse=True):
                del self[position]
            return
        position = _position(self, index)
        item = list.__getitem__(self, position)
        list.__delitem__(self, position)
        _record(RemoveItem(target=self, index=position, item=item))

    def __iadd__(self, items: Iterable[Any]) -> Self:  # type: ignore[override]
        self.extend(items)
        return self

    def __reduce__(self) -> tuple[Any, ...]:
        return (list, (list(self),))

    def __copy__(self) -> list:
        return list(self)

    def __deepcopy__(self, memo: dict[int, Any]) -> list:
        return copy.deepcopy(list(self), memo)

    def append(self, item: Any) -> None:
        self.insert(len(self), item)

    def extend(self, items: Iterable[Any]) -> None:
        for item in list(items):
            self.append(item)

    def insert(self, index: SupportsIndex, item: Any) -> None:
        item = self._adopt(item)
        position = max(0, min(int(index) if int(index) >= 0 else len(self) + int(index), len(self)))
        list.insert(self, position, item)
        _record(InsertItem(target=self, index=position, item=item))

    def remove(self, item: Any) -> None:
        del self[self.index(item)]

    def pop(self, index: SupportsIndex = -1) -> Any:
        position = _position(self, index)
        item = list.__getitem__(self, position)
        del self[position]
        return item

    def clear(self) -> None:
        del self[:]

    def sort(self, *args: Any, **kwargs: Any) -> None:
        self._reorder(sorted(self, *args, **kwargs))

    def reverse(self) -> None:
        self._reorder(list(reversed(self)))

    def _reorder(self, ordered: list[Any]) -> None:
        del self[:]
        for item in ordered:
            self.append(item)

    def _adopt(self, item: Any) -> Any:
        if not self.deep:
            return item
        return _adopt_nested(item, owner=self.owner, aspect=self.aspect, root_key=self.root_key)


def _adopt_nested(value: Any, *, owner: object, aspect: Aspect | None, root_key: Any) -> Any:
    # Only plain containers: a dict or list subclass is someone's own type, and keeps its behavior.
    if type(value) is dict:
        return JournaledDict(value, owner=owner, aspect=aspect, deep=True, root_key=root_key)
    if type(value) is list:
        return JournaledList(value, owner=owner, aspect=aspect, deep=True, root_key=root_key)
    return value


def _record(change: Change) -> None:
    transaction = _active.get()
    if transaction is not None:
        transaction.record(change)


def _replay(changes: list[Change], *, undoing: bool) -> list[str]:
    problems: list[str] = []
    applied: list[Change] = []
    with recording(None):
        for change in changes:
            try:
                moved = change.undo() if undoing else change.redo()
            except Conflict:
                _roll_back(applied, undoing=undoing)
                raise
            except Exception as err:
                logger.exception("Could not apply %r.", change)
                problems.append(f"One change could not be restored: {err}")
                continue
            if moved:
                applied.append(change)
    return problems


def _roll_back(applied: list[Change], *, undoing: bool) -> None:
    for change in reversed(applied):
        try:
            if undoing:
                change.redo()
            else:
                change.undo()
        except Exception:
            logger.exception("Could not roll back %r.", change)


def _move_item(target: dict, key: Any, current: Any, value: Any) -> bool:
    held = dict.get(target, key, MISSING)
    if _same(held, value):
        return False
    if not _same(held, current):
        raise Conflict(STALE)
    if value is MISSING:
        dict.pop(target, key, None)
    else:
        dict.__setitem__(target, key, value)
    return True


def _move_attribute(target: object, name: str, current: Any, value: Any) -> bool:
    held = target.__dict__.get(name, MISSING)
    if _same(held, value):
        return False
    if not _same(held, current):
        raise Conflict(STALE)
    if value is MISSING:
        target.__dict__.pop(name, None)
    else:
        object.__setattr__(target, name, value)
    return True


def _insert_into_list(target: list, index: int, item: Any) -> bool:
    if any(candidate is item for candidate in target):
        return False
    list.insert(target, min(index, len(target)), item)
    return True


def _remove_from_list(target: list, index: int, item: Any) -> bool:
    if 0 <= index < len(target) and target[index] is item:
        list.__delitem__(target, index)
        return True
    for position, candidate in enumerate(target):
        if candidate is item:
            list.__delitem__(target, position)
            return True
    return False


def _position(target: list, index: SupportsIndex) -> int:
    position = int(index)
    if position < 0:
        position += len(target)
    if not 0 <= position < len(target):
        msg = "list index out of range"
        raise IndexError(msg)
    return position


def _same(left: Any, right: Any) -> bool:
    if left is right:
        return True
    try:
        return bool(left == right)
    except Exception:
        return False
