"""Tests for the in-memory write_tracker module used by the artifact-stamping pipeline."""

import pytest

from griptape_nodes.files import write_tracker


class TestWriteTracker:
    @pytest.fixture(autouse=True)
    def _clear(self) -> None:
        write_tracker.clear()

    def test_record_then_lookup(self) -> None:
        write_tracker.record("key-a", 1700000000000000000)
        assert write_tracker.lookup("key-a") is not None

    def test_lookup_missing_returns_none(self) -> None:
        assert write_tracker.lookup("/nope") is None

    def test_overwrite_replaces_token(self) -> None:
        write_tracker.record("key-a", 1700000000000000000)
        first = write_tracker.lookup("key-a")
        write_tracker.record("key-a", 1700000001000000000)
        second = write_tracker.lookup("key-a")
        assert first != second

    def test_alias_copies_token(self) -> None:
        write_tracker.record("key-a", 1700000000000000000)
        write_tracker.alias("key-mapped", "key-a")
        assert write_tracker.lookup("key-mapped") == write_tracker.lookup("key-a")

    def test_alias_unknown_source_is_noop(self) -> None:
        write_tracker.alias("key-mapped", "/never-recorded")
        assert write_tracker.lookup("key-mapped") is None

    def test_lru_eviction_drops_oldest(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(write_tracker, "MAX_ENTRIES", 2)
        write_tracker.record("a", 1)
        write_tracker.record("b", 2)
        write_tracker.record("c", 3)  # evicts "a"
        assert write_tracker.lookup("a") is None
        assert write_tracker.lookup("b") is not None
        assert write_tracker.lookup("c") is not None

    def test_record_refreshes_lru_position(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(write_tracker, "MAX_ENTRIES", 2)
        write_tracker.record("a", 1)
        write_tracker.record("b", 2)
        # Re-recording "a" should make "b" the LRU candidate.
        write_tracker.record("a", 10)
        write_tracker.record("c", 3)
        assert write_tracker.lookup("a") is not None
        assert write_tracker.lookup("b") is None
        assert write_tracker.lookup("c") is not None

    def test_token_is_iso8601_utc(self) -> None:
        write_tracker.record("/x", 1700000000000000000)
        token = write_tracker.lookup("/x")
        assert token is not None
        assert token.endswith("+00:00")

    def test_clear_drops_all_entries(self) -> None:
        write_tracker.record("/x", 1)
        write_tracker.clear()
        assert write_tracker.lookup("/x") is None
