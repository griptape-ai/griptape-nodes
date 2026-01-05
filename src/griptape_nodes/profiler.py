"""Startup profiler for tracking import and initialization times.

Enable profiling by setting environment variable:
    GRIPTAPE_NODES_PROFILE=1 uv run griptape-nodes

This will output detailed timing information to stderr showing:
- Import times for major modules
- Initialization times for key components
- Total startup time

Output is saved to: profiles/startup_profile_<timestamp>.json
"""

import importlib.util
import json
import os
import sys
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

# Check if profiling is enabled
PROFILING_ENABLED = os.environ.get("GRIPTAPE_NODES_PROFILE", "0") == "1"


class StartupProfiler:
    """Tracks import and initialization times during application startup."""

    def __init__(self):
        self.start_time = time.perf_counter()
        self.events: list[dict[str, Any]] = []
        self.import_times: dict[str, float] = {}
        self.original_import: Any = None

    def record_event(self, event_type: str, name: str, duration: float, metadata: dict[str, Any] | None = None):
        """Record a profiling event."""
        if not PROFILING_ENABLED:
            return

        event = {
            "type": event_type,
            "name": name,
            "duration_ms": duration * 1000,
            "timestamp": time.perf_counter() - self.start_time,
            "metadata": metadata or {},
        }
        self.events.append(event)

    @contextmanager
    def measure(self, event_type: str, name: str, metadata: dict[str, Any] | None = None):
        """Context manager for measuring execution time."""
        if not PROFILING_ENABLED:
            yield
            return

        start = time.perf_counter()
        try:
            yield
        finally:
            duration = time.perf_counter() - start
            self.record_event(event_type, name, duration, metadata)

    def start_import_tracking(self):
        """Start tracking import times."""
        if not PROFILING_ENABLED:
            return

        # Handle both dict and module forms of __builtins__
        import builtins

        self.original_import = builtins.__import__

        def tracking_import(name, *args, **kwargs):
            # Only track griptape and griptape_nodes imports
            if name.startswith(("griptape", "griptape_nodes")):
                start = time.perf_counter()
                try:
                    result = self.original_import(name, *args, **kwargs)
                    duration = time.perf_counter() - start
                    # Accumulate time for each module
                    if name not in self.import_times:
                        self.import_times[name] = 0
                    self.import_times[name] += duration
                    return result
                except Exception:
                    raise
            else:
                return self.original_import(name, *args, **kwargs)

        builtins.__import__ = tracking_import

    def stop_import_tracking(self):
        """Stop tracking import times and record results."""
        if not PROFILING_ENABLED:
            return

        if self.original_import:
            import builtins

            builtins.__import__ = self.original_import

        # Record import times as events
        for module, duration in sorted(self.import_times.items(), key=lambda x: x[1], reverse=True):
            self.record_event("import", module, duration)

    def save_profile(self):
        """Save profile data to file."""
        if not PROFILING_ENABLED:
            return

        total_time = time.perf_counter() - self.start_time

        # Create profiles directory
        profile_dir = Path("profiles")
        profile_dir.mkdir(exist_ok=True)

        # Generate filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        profile_file = profile_dir / f"startup_profile_{timestamp}.json"

        # Prepare summary statistics
        import_events = [e for e in self.events if e["type"] == "import"]
        total_import_time = sum(e["duration_ms"] for e in import_events)

        griptape_imports = [e for e in import_events if "griptape." in e["name"]]
        total_griptape_time = sum(e["duration_ms"] for e in griptape_imports)

        summary = {
            "total_startup_time_ms": total_time * 1000,
            "total_import_time_ms": total_import_time,
            "total_griptape_import_time_ms": total_griptape_time,
            "num_imports": len(import_events),
            "num_griptape_imports": len(griptape_imports),
            "timestamp": datetime.now().isoformat(),
        }

        # Group events by type
        events_by_type = {}
        for event in self.events:
            event_type = event["type"]
            if event_type not in events_by_type:
                events_by_type[event_type] = []
            events_by_type[event_type].append(event)

        profile_data = {
            "summary": summary,
            "events_by_type": events_by_type,
            "all_events": self.events,
        }

        # Save to file
        with open(profile_file, "w") as f:
            json.dump(profile_data, f, indent=2)

        # Print summary to stderr
        self._print_summary(summary, profile_file)

    def _print_summary(self, summary: dict[str, Any], profile_file: Path):
        """Print summary to stderr."""
        print("\n" + "=" * 80, file=sys.stderr)
        print("STARTUP PROFILE SUMMARY", file=sys.stderr)
        print("=" * 80, file=sys.stderr)
        print(f"Total startup time: {summary['total_startup_time_ms']:.1f}ms", file=sys.stderr)
        print(f"Total import time: {summary['total_import_time_ms']:.1f}ms", file=sys.stderr)
        print(f"  - Griptape imports: {summary['total_griptape_import_time_ms']:.1f}ms", file=sys.stderr)
        print(f"Total imports tracked: {summary['num_imports']}", file=sys.stderr)
        print(f"  - Griptape modules: {summary['num_griptape_imports']}", file=sys.stderr)
        print(f"\nProfile saved to: {profile_file}", file=sys.stderr)
        print("=" * 80 + "\n", file=sys.stderr)

        # Show top 10 slowest imports
        import_events = [e for e in self.events if e["type"] == "import"]
        if import_events:
            print("Top 10 slowest imports:", file=sys.stderr)
            sorted_imports = sorted(import_events, key=lambda x: x["duration_ms"], reverse=True)[:10]
            for i, event in enumerate(sorted_imports, 1):
                print(f"  {i}. {event['name']}: {event['duration_ms']:.1f}ms", file=sys.stderr)
            print(file=sys.stderr)


# Global profiler instance
_profiler = StartupProfiler()


def get_profiler() -> StartupProfiler:
    """Get the global profiler instance."""
    return _profiler


def is_profiling_enabled() -> bool:
    """Check if profiling is enabled."""
    return PROFILING_ENABLED
