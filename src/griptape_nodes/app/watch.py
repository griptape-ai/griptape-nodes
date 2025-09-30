from __future__ import annotations

import subprocess
import sys

from watchfiles import DefaultFilter, watch

from griptape_nodes.utils.uv_utils import find_uv_bin


def start_process() -> subprocess.Popen:
    """Start the gtn process."""
    uv_path = find_uv_bin()
    return subprocess.Popen(  # noqa: S603
        [uv_path, "run", "gtn"],
        stdout=sys.stdout,
        stderr=sys.stderr,
    )


def terminate_process(process: subprocess.Popen) -> None:
    """Gracefully terminate a process with timeout."""
    if process.poll() is not None:
        return  # Process already terminated

    # First try graceful termination
    process.terminate()
    try:
        # Wait up to 5 seconds for graceful shutdown
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        # Force kill if it doesn't shut down gracefully
        process.kill()
        process.wait()


if __name__ == "__main__":
    # Configure filter to ignore .venv, __pycache__, and compiled Python files
    watch_filter = DefaultFilter(
        ignore_dirs=(".venv",),
        ignore_entity_patterns=(r"\.pyc$", r"\.pyo$"),
    )

    process = start_process()

    try:
        # Watch for changes in src, libraries, and tests directories
        for changes in watch("src", "libraries", "tests", watch_filter=watch_filter):
            # Only restart on .py file changes
            if any(str(path).endswith(".py") for _, path in changes):
                terminate_process(process)
                process = start_process()
    except KeyboardInterrupt:
        terminate_process(process)
