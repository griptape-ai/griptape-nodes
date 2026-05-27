"""In-memory registry of recent file writes, keyed by the artifact-facing path string.

The artifact pipeline emits ``UrlArtifact(value=<path>)`` whenever a node saves
output. The frontend keys its preview-cache invalidation on
``meta.created_at`` (see ``hooks/useConvertFileUrl.ts``), so when a node
overwrites a file at the same path the editor must see a fresh ``created_at``
or its presigned URL stays cached and the preview never re-fetches.

``OSManager.on_write_file_request`` records the post-write mtime under the
resolved absolute path. Downstream layers (``File``, ``ProjectFileDestination``,
``StaticFilesManager``) call ``alias`` to mirror that token under whatever
spelling the artifact's ``.value`` will actually carry (macro template,
project-mapped macro, signed download URL). The cattrs unstructure hook in
``retained_mode.events.event_converter`` then stamps ``meta.created_at`` with
a single in-memory dict lookup at serialization time -- no I/O, no macro
resolution, no manager calls during serialize.

Bounded LRU so a long-running engine doesn't accumulate every write forever.
The cache only needs to outlive the round-trip from ``write_bytes`` to the
ParameterValueUpdateEvent emit, typically well under a second.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from datetime import UTC, datetime

MAX_ENTRIES = 8192

_cache: OrderedDict[str, str] = OrderedDict()
_lock = threading.Lock()


def record(key: str, mtime_ns: int) -> None:
    """Record an mtime token for one spelling of a written path."""
    token = datetime.fromtimestamp(mtime_ns / 1e9, tz=UTC).isoformat()
    with _lock:
        _set_locked(key, token)


def alias(new_key: str, source_key: str) -> None:
    """Copy the token recorded under ``source_key`` to ``new_key``.

    Each write records under the resolved absolute path at the OSManager
    chokepoint. Aliases cover the other spellings an artifact's ``.value``
    may carry: the originating ``File.location`` macro template, the
    ``ProjectFileDestination``-mapped portable form (``{outputs}/foo.png``),
    and the signed download URL emitted by ``StaticFilesManager``. No-op if
    ``source_key`` is unknown.
    """
    with _lock:
        token = _cache.get(source_key)
        if token is None:
            return
        _set_locked(new_key, token)


def lookup(key: str) -> str | None:
    """Return the recorded ISO8601 token for ``key`` or None."""
    with _lock:
        return _cache.get(key)


def clear() -> None:
    """Drop all entries. Test hook."""
    with _lock:
        _cache.clear()


def _set_locked(key: str, token: str) -> None:
    """Insert/refresh ``key`` and evict to ``MAX_ENTRIES``. Caller holds ``_lock``."""
    if key in _cache:
        _cache.move_to_end(key)
    _cache[key] = token
    while len(_cache) > MAX_ENTRIES:
        _cache.popitem(last=False)
