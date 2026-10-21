"""How long one node's pre-run input checks may spend probing its video and audio inputs.

The engine opens `input_check_budget` around each node's `validate_before_node_run`. It lives apart
from `input_checks` so the resolution machine can open it without importing Pillow, pillow-heif or
static-ffmpeg.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator

__all__ = ["VALIDATION_PROBE_BUDGET_SECONDS", "input_check_budget", "probe_deadline"]

# How long after a node's validation starts it may still probe video and audio inputs. Once this much
# time has passed, the remaining inputs are skipped rather than probed, so one node's slow probes
# can't add up.
# It counts all of the validation's time, not only probing. The cap is per node: when the engine
# starts several nodes in one pass, each can block for this long.
VALIDATION_PROBE_BUDGET_SECONDS = 5

# When the current validation run's probe budget runs out, as a `time.monotonic()` reading, or None
# outside a run.
_probe_deadline: ContextVar[float | None] = ContextVar("input_check_probe_deadline", default=None)


@contextmanager
def input_check_budget(seconds: float = VALIDATION_PROBE_BUDGET_SECONDS) -> Iterator[None]:
    """Stop the video and audio probes inside this block once `seconds` have passed since it opened.

    The engine opens one around each node's `validate_before_node_run`, so a node checking several
    video or audio inputs probes for at most `seconds` in all. The time counts from when the block
    opens, so it includes any other checks the node runs first. Inside it, each probe gets the smaller
    of `input_checks.FFPROBE_TIMEOUT_SECONDS` and the time left, and a probe that would start with no
    time left is skipped. Opened inside another budget, it can shorten the time left but never extend it.
    """
    deadline = time.monotonic() + seconds
    # Nested inside another budget, this one can only end sooner, so the engine's cap always holds.
    outer = _probe_deadline.get()
    if outer is not None and outer < deadline:
        deadline = outer
    token = _probe_deadline.set(deadline)
    try:
        yield
    finally:
        _probe_deadline.reset(token)


def probe_deadline() -> float | None:
    """When the current budget runs out, as a `time.monotonic()` reading, or None outside one."""
    return _probe_deadline.get()
