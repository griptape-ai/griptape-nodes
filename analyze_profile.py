#!/usr/bin/env python3
"""Analyze startup profile data.

Usage:
    python analyze_profile.py profiles/startup_profile_*.json
"""

import json
import sys
from pathlib import Path


def analyze_profile(profile_file: Path):
    """Analyze and display profile data."""
    with open(profile_file) as f:
        data = json.load(f)

    summary = data["summary"]
    events_by_type = data["events_by_type"]

    print(f"\n{'=' * 80}")
    print(f"Profile: {profile_file.name}")
    print(f"{'=' * 80}")

    # Summary
    print("\nSUMMARY:")
    print(f"  Total startup time: {summary['total_startup_time_ms']:.1f}ms")
    print(f"  Total import time: {summary['total_import_time_ms']:.1f}ms")
    print(f"    - Griptape imports: {summary['total_griptape_import_time_ms']:.1f}ms")
    print(f"  Total imports: {summary['num_imports']}")
    print(f"    - Griptape modules: {summary['num_griptape_imports']}")

    # Breakdown by event type
    print("\nBREAKDOWN BY EVENT TYPE:")
    for event_type, events in events_by_type.items():
        total_time = sum(e["duration_ms"] for e in events)
        print(f"  {event_type}: {total_time:.1f}ms ({len(events)} events)")

    # Top imports
    if "import" in events_by_type:
        imports = events_by_type["import"]
        print("\nTOP 20 SLOWEST IMPORTS:")
        sorted_imports = sorted(imports, key=lambda x: x["duration_ms"], reverse=True)[:20]
        for i, event in enumerate(sorted_imports, 1):
            name = event["name"]
            duration = event["duration_ms"]
            # Show hierarchy with indentation
            indent = "  " * (name.count("."))
            print(f"  {i:2d}. {indent}{name.split('.')[-1]}: {duration:.1f}ms")

    # Griptape-specific analysis
    if "import" in events_by_type:
        imports = events_by_type["import"]
        griptape_imports = [e for e in imports if "griptape." in e["name"]]

        if griptape_imports:
            print("\nGRIPTAPE MODULE ANALYSIS:")
            # Group by top-level module
            top_level_times = {}
            for imp in griptape_imports:
                parts = imp["name"].split(".")
                if len(parts) >= 2:
                    top_level = f"{parts[0]}.{parts[1]}"
                    if top_level not in top_level_times:
                        top_level_times[top_level] = 0
                    top_level_times[top_level] += imp["duration_ms"]

            sorted_modules = sorted(top_level_times.items(), key=lambda x: x[1], reverse=True)[:10]
            for module, duration in sorted_modules:
                print(f"  {module}: {duration:.1f}ms")

    # Other event types
    for event_type in ["init", "execution"]:
        if event_type in events_by_type:
            events = events_by_type[event_type]
            if events:
                print(f"\n{event_type.upper()} EVENTS:")
                for event in sorted(events, key=lambda x: x["duration_ms"], reverse=True):
                    print(f"  {event['name']}: {event['duration_ms']:.1f}ms")


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python analyze_profile.py profiles/startup_profile_*.json")
        sys.exit(1)

    profile_files = [Path(arg) for arg in sys.argv[1:]]

    for profile_file in profile_files:
        if not profile_file.exists():
            print(f"Error: File not found: {profile_file}")
            continue

        analyze_profile(profile_file)

    print()


if __name__ == "__main__":
    main()
