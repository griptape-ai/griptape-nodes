import os
import threading
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest
from watchfiles import Change

from griptape_nodes.retained_mode.managers import static_file_watcher
from griptape_nodes.retained_mode.managers.static_file_watcher import StaticFileWatcher, WatchedFileChange


class Recorder:
    def __init__(self) -> None:
        self.changes: list[WatchedFileChange] = []
        self.received = threading.Event()

    def __call__(self, change: WatchedFileChange) -> None:
        self.changes.append(change)
        self.received.set()


@pytest.fixture
def recorder() -> Recorder:
    """Collect the changes a watcher reports."""
    return Recorder()


@pytest.fixture
def watcher(recorder: Recorder) -> Generator[StaticFileWatcher, None, None]:
    """A watcher using OS notifications, stopped after the test."""
    file_watcher = StaticFileWatcher(on_change=recorder, debounce_ms=50)
    yield file_watcher
    file_watcher.stop()


@pytest.fixture
def idle_watcher(recorder: Recorder, monkeypatch: pytest.MonkeyPatch) -> StaticFileWatcher:
    """A watcher whose background thread never starts.

    For tests that call handle_changes and recheck_all themselves. A running thread would see the
    test's own saves and report them first, which makes what the test observes depend on timing.
    """
    monkeypatch.setattr(StaticFileWatcher, "_start_thread_if_needed", lambda _self: None)
    return StaticFileWatcher(on_change=recorder)


def rewrite(path: Path, content: bytes) -> None:
    """Replace a file the way most apps save: write a temp file, then rename it over the original."""
    temp_path = path.with_name(f".{path.name}.tmp")
    temp_path.write_bytes(content)
    temp_path.replace(path)


class TestHandleChanges:
    def test_reports_a_watched_file_that_changed_with_every_spelling(
        self, idle_watcher: StaticFileWatcher, recorder: Recorder, tmp_path: Path
    ) -> None:
        image = tmp_path / "plate.png"
        image.write_bytes(b"v1")
        idle_watcher.watch_file(image, "{inputs}/plate.png")
        idle_watcher.watch_file(image, image.as_uri())

        rewrite(image, b"version two")
        idle_watcher.handle_changes({(Change.added, str(image))})

        assert [change.requested_file_paths for change in recorder.changes] == [["{inputs}/plate.png", image.as_uri()]]

    def test_ignores_events_that_leave_the_file_unchanged(
        self, idle_watcher: StaticFileWatcher, recorder: Recorder, tmp_path: Path
    ) -> None:
        image = tmp_path / "plate.png"
        image.write_bytes(b"v1")
        idle_watcher.watch_file(image, str(image))

        idle_watcher.handle_changes({(Change.modified, str(image))})

        assert recorder.changes == []

    def test_reports_each_change_once(
        self, idle_watcher: StaticFileWatcher, recorder: Recorder, tmp_path: Path
    ) -> None:
        image = tmp_path / "plate.png"
        image.write_bytes(b"v1")
        idle_watcher.watch_file(image, str(image))

        rewrite(image, b"version two")
        idle_watcher.handle_changes({(Change.added, str(image))})
        idle_watcher.handle_changes({(Change.modified, str(image))})

        assert len(recorder.changes) == 1

    def test_ignores_files_nobody_asked_about(
        self, idle_watcher: StaticFileWatcher, recorder: Recorder, tmp_path: Path
    ) -> None:
        image = tmp_path / "plate.png"
        image.write_bytes(b"v1")
        idle_watcher.watch_file(image, str(image))
        neighbor = tmp_path / "neighbor.png"
        neighbor.write_bytes(b"other")

        idle_watcher.handle_changes({(Change.added, str(neighbor))})

        assert recorder.changes == []

    def test_skips_a_file_that_is_missing_when_the_batch_arrives(
        self, idle_watcher: StaticFileWatcher, recorder: Recorder, tmp_path: Path
    ) -> None:
        image = tmp_path / "plate.png"
        image.write_bytes(b"v1")
        idle_watcher.watch_file(image, str(image))

        image.unlink()
        idle_watcher.handle_changes({(Change.deleted, str(image))})

        assert recorder.changes == []

    def test_minting_again_sets_a_new_baseline(
        self, idle_watcher: StaticFileWatcher, recorder: Recorder, tmp_path: Path
    ) -> None:
        image = tmp_path / "plate.png"
        image.write_bytes(b"v1")
        idle_watcher.watch_file(image, str(image))

        # The client re-requested after the change and already holds the new URL.
        rewrite(image, b"version two")
        idle_watcher.watch_file(image, str(image))
        idle_watcher.handle_changes({(Change.added, str(image))})

        assert recorder.changes == []


class TestRecheckAll:
    def test_reports_a_change_no_event_mentioned(
        self, idle_watcher: StaticFileWatcher, recorder: Recorder, tmp_path: Path
    ) -> None:
        image = tmp_path / "plate.png"
        image.write_bytes(b"v1")
        untouched = tmp_path / "untouched.png"
        untouched.write_bytes(b"same")
        idle_watcher.watch_file(image, "plate")
        idle_watcher.watch_file(untouched, "untouched")

        rewrite(image, b"version two")
        idle_watcher.recheck_all()

        assert [change.requested_file_paths for change in recorder.changes] == [["plate"]]


class TestWatchFile:
    def test_two_spellings_of_one_file_share_one_entry(self, idle_watcher: StaticFileWatcher, tmp_path: Path) -> None:
        image = tmp_path / "plate.png"
        image.write_bytes(b"v1")

        idle_watcher.watch_file(image, "a")
        idle_watcher.watch_file(tmp_path / "sub" / ".." / "plate.png", "b")

        assert len(idle_watcher.watched_paths) == 1

    def test_drops_the_least_recently_requested_file_past_the_limit(self, recorder: Recorder, tmp_path: Path) -> None:
        file_watcher = StaticFileWatcher(on_change=recorder, max_files=2, force_polling=True)
        try:
            paths = []
            for name in ("a.png", "b.png", "c.png"):
                path = tmp_path / name
                path.write_bytes(name.encode())
                paths.append(path)
            file_watcher.watch_file(paths[0], "a")
            file_watcher.watch_file(paths[1], "b")
            # Asking for a.png again makes b.png the least recently requested.
            file_watcher.watch_file(paths[0], "a")
            file_watcher.watch_file(paths[2], "c")

            assert [path.name for path in file_watcher.watched_paths] == ["a.png", "c.png"]
        finally:
            file_watcher.stop()


class TestWatcherThread:
    def test_reports_a_file_saved_by_another_app(
        self, watcher: StaticFileWatcher, recorder: Recorder, tmp_path: Path
    ) -> None:
        image = tmp_path / "plate.png"
        image.write_bytes(b"v1")
        watcher.watch_file(image, "{inputs}/plate.png")
        # Give the thread time to start its first watch, so the save lands inside it.
        threading.Event().wait(0.5)

        rewrite(image, b"version two")

        assert recorder.received.wait(timeout=10)
        assert recorder.changes[0].requested_file_paths == ["{inputs}/plate.png"]

    def test_picks_up_a_file_in_a_folder_added_while_running(
        self, watcher: StaticFileWatcher, recorder: Recorder, tmp_path: Path
    ) -> None:
        first = tmp_path / "first" / "a.png"
        first.parent.mkdir()
        first.write_bytes(b"a")
        watcher.watch_file(first, "a")
        threading.Event().wait(0.5)

        second = tmp_path / "second" / "b.png"
        second.parent.mkdir()
        second.write_bytes(b"b")
        watcher.watch_file(second, "b")
        threading.Event().wait(0.5)

        # An in-place write, as some apps save.
        with second.open("ab") as handle:
            handle.write(b" more")
            handle.flush()
            os.fsync(handle.fileno())

        assert recorder.received.wait(timeout=10)
        assert recorder.changes[0].requested_file_paths == ["b"]

    def test_catches_a_quick_resave_that_polling_misses(self, recorder: Recorder, tmp_path: Path) -> None:
        # Polling compares whole-second times, so a save within a second of the last write sends
        # no event. The periodic re-check still reports it.
        file_watcher = StaticFileWatcher(
            on_change=recorder, debounce_ms=50, recheck_interval_ms=200, force_polling=True
        )
        try:
            image = tmp_path / "plate.png"
            image.write_bytes(b"v1")
            file_watcher.watch_file(image, "plate")
            threading.Event().wait(0.1)

            rewrite(image, b"version two")

            assert recorder.received.wait(timeout=10)
            assert recorder.changes[0].requested_file_paths == ["plate"]
        finally:
            file_watcher.stop()

    def test_keeps_working_after_every_watched_folder_is_deleted(
        self, watcher: StaticFileWatcher, recorder: Recorder, tmp_path: Path
    ) -> None:
        gone = tmp_path / "gone" / "a.png"
        gone.parent.mkdir()
        gone.write_bytes(b"a")
        watcher.watch_file(gone, "a")
        threading.Event().wait(0.3)
        gone.unlink()
        gone.parent.rmdir()
        # A file in a folder that doesn't exist restarts the watch with no folder left to watch.
        watcher.watch_file(tmp_path / "missing" / "x.png", "x")
        threading.Event().wait(0.3)

        # With nothing left to watch, the thread waits for the next file instead of exiting.
        kept = tmp_path / "kept" / "b.png"
        kept.parent.mkdir()
        kept.write_bytes(b"b")
        watcher.watch_file(kept, "b")
        threading.Event().wait(0.5)
        rewrite(kept, b"b, saved again")

        assert recorder.received.wait(timeout=10)
        assert recorder.changes[0].requested_file_paths == ["b"]

    def test_retries_after_the_watch_fails(
        self, recorder: Recorder, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        real_watch = static_file_watcher.watch
        calls = []

        def watch_that_fails_once(*args: Any, **kwargs: Any) -> Any:
            calls.append(args)
            if len(calls) == 1:
                msg = "No path was found."
                raise FileNotFoundError(msg)
            return real_watch(*args, **kwargs)

        monkeypatch.setattr(static_file_watcher, "watch", watch_that_fails_once)
        monkeypatch.setattr(static_file_watcher, "RETRY_DELAY_S", 0.05)
        file_watcher = StaticFileWatcher(on_change=recorder, debounce_ms=50)
        try:
            image = tmp_path / "plate.png"
            image.write_bytes(b"v1")
            file_watcher.watch_file(image, "plate")
            threading.Event().wait(0.5)

            rewrite(image, b"version two")

            assert recorder.received.wait(timeout=10)
            # The first watch failed, so the change came from a later one.
            assert len(calls) > 1
            assert "Attempted to watch 1 folders for changes to previewed files" in caplog.text
        finally:
            file_watcher.stop()
