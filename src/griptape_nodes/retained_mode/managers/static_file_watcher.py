"""Watch the local files behind minted download URLs and report when one changes on disk."""

import logging
import os
import threading
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import NamedTuple

from watchfiles import Change, watch

from griptape_nodes.files.path_utils import canonicalize_for_identity, canonicalize_for_io

logger = logging.getLogger("griptape_nodes")

# Most files watched at once. A long session mints a URL for every preview it shows, so the
# oldest fall off instead of letting the set, and the directories under watch, grow without bound.
MAX_WATCHED_FILES = 1000

# How long to group filesystem events before reporting. Apps save in bursts (write a temp file,
# rename it over the original), and one report per save is enough.
DEBOUNCE_MS = 300

# How often to compare every watched file against its last fingerprint while no events arrive.
# Filesystem events can be missed: a save landing while the watch restarts, or a second save within
# the same second when watchfiles falls back to polling, which compares whole-second times.
RECHECK_INTERVAL_MS = 5000

# How long to wait before watching again after the watch itself failed, such as when a watched
# directory was deleted between listing it and starting the watch.
RETRY_DELAY_S = 5.0


class FileFingerprint(NamedTuple):
    """The file identity the local storage driver versions URLs by.

    A new inode, size, or modification time means the next minted URL differs, so a change is
    worth reporting. Matching fingerprints mean it is not.
    """

    inode: int
    size: int
    mtime_ns: int


class WatchedFileChange(NamedTuple):
    """A watched file that changed on disk.

    Attributes:
        path: Canonical absolute path of the file.
        requested_file_paths: Every spelling a client asked for this file by, in first-seen order.
    """

    path: Path
    requested_file_paths: list[str]


@dataclass
class WatchedFile:
    """A file under watch, the last fingerprint seen for it, and how clients asked for it."""

    fingerprint: FileFingerprint | None
    requested_file_paths: list[str] = field(default_factory=list)


class StaticFileWatcher:
    """Watch files on disk and call back when one is saved or replaced.

    watchfiles cannot add paths to a running watch, so one background thread watches the parent
    directories of the watched files and restarts its watch whenever that set of directories
    changes. Directories are watched non-recursively, and events for files nobody asked about are
    ignored. Every watched file is also re-checked when a watch starts and whenever events go
    quiet for a while, which catches changes the events missed. The thread starts with the first
    watched file, so an engine that never watches anything never starts it.
    """

    def __init__(
        self,
        on_change: Callable[[WatchedFileChange], None],
        *,
        max_files: int = MAX_WATCHED_FILES,
        debounce_ms: int = DEBOUNCE_MS,
        recheck_interval_ms: int = RECHECK_INTERVAL_MS,
        force_polling: bool | None = None,
    ) -> None:
        """Create a watcher that is idle until the first call to watch_file.

        Args:
            on_change: Called on the watcher's thread once per changed file.
            max_files: Most files watched at once. The least recently requested fall off first.
            debounce_ms: How long to group filesystem events before reporting them.
            recheck_interval_ms: How often to re-check every watched file while no events arrive.
            force_polling: Passed to watchfiles. None lets it decide; True polls instead of using
                OS notifications, which network drives need.
        """
        self._on_change = on_change
        self._max_files = max_files
        self._debounce_ms = debounce_ms
        self._recheck_interval_ms = recheck_interval_ms
        self._force_polling = force_polling
        self._lock = threading.Lock()
        self._files: OrderedDict[Path, WatchedFile] = OrderedDict()
        # Set to make the thread pick up a new set of directories. Also the watch's stop event.
        self._restart = threading.Event()
        self._shutdown = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def watched_paths(self) -> list[Path]:
        """Canonical paths of the files under watch, least recently requested first."""
        with self._lock:
            return list(self._files)

    def watch_file(self, path: Path, requested_file_path: str) -> None:
        """Start watching a file, or record another spelling for one already watched.

        Args:
            path: Absolute path of the file on disk.
            requested_file_path: The path as the client sent it, reported back on change so the
                client can match it to what it is showing.
        """
        key = canonicalize_for_identity(path)
        # Read before taking the lock. On a slow network drive a stat can take seconds, and the
        # watcher thread waits on the lock.
        fingerprint = _fingerprint(key)
        with self._lock:
            directories_before = self._directories()
            watched = self._files.get(key)
            if watched is None:
                watched = WatchedFile(fingerprint=fingerprint)
                self._files[key] = watched
            else:
                # The client just minted a URL from the file as it is now, so this is the
                # baseline the next change is measured against.
                watched.fingerprint = fingerprint
                self._files.move_to_end(key)
            if requested_file_path not in watched.requested_file_paths:
                watched.requested_file_paths.append(requested_file_path)
            while len(self._files) > self._max_files:
                self._files.popitem(last=False)
            directories_changed = self._directories() != directories_before
            self._start_thread_if_needed()

        if directories_changed:
            self._restart.set()

    def stop(self) -> None:
        """Stop the watcher thread. The watcher can't be restarted afterwards."""
        self._shutdown.set()
        self._restart.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)

    def handle_changes(self, changes: set[tuple[Change, str]]) -> None:
        """Report each watched file in a batch of filesystem events whose fingerprint changed."""
        self._report_changed({canonicalize_for_identity(path_str) for _change, path_str in changes})

    def recheck_all(self) -> None:
        """Report every watched file whose fingerprint changed, whether or not an event said so."""
        with self._lock:
            paths = set(self._files)
        self._report_changed(paths)

    def _report_changed(self, paths: set[Path]) -> None:
        """Report each of these watched files whose fingerprint changed since it was last seen.

        A file that is missing right now is skipped. Atomic saves remove the original before
        renaming the new file into place, and the event for that rename reports the new file.
        """
        with self._lock:
            watched_paths = [path for path in paths if path in self._files]
        # Stat outside the lock, so a slow drive doesn't hold up watch_file, which the URL request
        # handler calls.
        fingerprints = {path: _fingerprint(path) for path in watched_paths}

        reports: list[WatchedFileChange] = []
        with self._lock:
            for path, fingerprint in fingerprints.items():
                watched = self._files.get(path)
                if watched is None:
                    continue
                if fingerprint is None:
                    continue
                if fingerprint == watched.fingerprint:
                    continue
                watched.fingerprint = fingerprint
                reports.append(WatchedFileChange(path=path, requested_file_paths=list(watched.requested_file_paths)))

        # Outside the lock, so a callback that watches another file doesn't deadlock.
        for report in reports:
            self._on_change(report)

    def _start_thread_if_needed(self) -> None:
        if self._thread is not None or self._shutdown.is_set():
            return
        self._thread = threading.Thread(target=self._run, name="WatchFiles-StaticFiles", daemon=True)
        self._thread.start()

    def _directories(self) -> set[Path]:
        return {path.parent for path in self._files}

    def _run(self) -> None:
        while not self._shutdown.is_set():
            # Clear before listing the directories, so a file watched after the listing sets the
            # event again and the watch below restarts to include it.
            self._restart.clear()
            with self._lock:
                listed = sorted(self._directories())
            # Checked outside the lock, for the same reason as the stats in _report_changed.
            directories = [directory for directory in listed if directory.is_dir()]
            if not directories:
                self._restart.wait()
                continue

            # Catches a save that landed while the previous watch was stopping.
            self.recheck_all()
            try:
                for changes in watch(
                    *directories,
                    watch_filter=None,
                    debounce=self._debounce_ms,
                    stop_event=self._restart,
                    rust_timeout=self._recheck_interval_ms,
                    yield_on_timeout=True,
                    recursive=False,
                    raise_interrupt=False,
                    force_polling=self._force_polling,
                    ignore_permission_denied=True,
                ):
                    # An empty batch means the timeout passed with no events.
                    if changes:
                        self.handle_changes(changes)
                    else:
                        self.recheck_all()
            # watchfiles raises RuntimeError (WatchfilesRustInternalError) for errors during a running
            # watch, such as a file name in a watched folder that isn't valid UTF-8.
            except (OSError, RuntimeError) as e:
                logger.warning(
                    "Attempted to watch %d folders for changes to previewed files. Failed due to %s. "
                    "Trying again in %.0f seconds.",
                    len(directories),
                    e,
                    RETRY_DELAY_S,
                )
                self._restart.wait(RETRY_DELAY_S)


def _fingerprint(path: Path) -> FileFingerprint | None:
    try:
        stat_result = os.stat(canonicalize_for_io(path))  # noqa: PTH116
    except OSError:
        return None
    return FileFingerprint(inode=stat_result.st_ino, size=stat_result.st_size, mtime_ns=stat_result.st_mtime_ns)
