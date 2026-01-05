# Startup Profiling

This document explains how to profile the startup performance of Griptape Nodes to identify import and initialization bottlenecks.

## Quick Start

### Profile CLI startup

```bash
# Profile --version (fastest command)
make profile ARGS="--version"

# Profile --help
make profile ARGS="--help"

# Profile config command
make profile ARGS="config show workspace_directory"
```

### Analyze profiles

```bash
# Analyze the most recent profile
python analyze_profile.py profiles/startup_profile_*.json

# Analyze a specific profile
python analyze_profile.py profiles/startup_profile_20231229_150330.json
```

### Profile with Python's importtime

For detailed Python-level import analysis:

```bash
make importtime
```

This creates `importtime.log` with microsecond-level timing for every import.

## Understanding the Results

### Profile Output

When profiling is enabled, you'll see output like:

```
================================================================================
STARTUP PROFILE SUMMARY
================================================================================
Total startup time: 1146.4ms
Total import time: 5101.2ms
  - Griptape imports: 1003.4ms
Total imports tracked: 386
  - Griptape modules: 226

Profile saved to: profiles/startup_profile_20251229_150330.json
================================================================================

Top 10 slowest imports:
  1. griptape_nodes.cli.main: 1143.9ms
  2. griptape_nodes.cli.commands: 1058.3ms
  3. griptape_nodes.retained_mode.managers.agent_manager: 756.9ms
  ...
```

### Key Metrics

- **Total startup time**: Time from script start to command execution
- **Total import time**: Cumulative time spent importing modules
- **Griptape imports**: Time spent importing the Griptape framework
- **Top slowest imports**: Modules that take the longest to import

### Profile JSON Structure

The profile JSON contains:

```json
{
  "summary": {
    "total_startup_time_ms": 1146.4,
    "total_import_time_ms": 5101.2,
    "total_griptape_import_time_ms": 1003.4,
    "num_imports": 386,
    "num_griptape_imports": 226
  },
  "events_by_type": {
    "import": [...],
    "init": [...],
    "execution": [...]
  }
}
```

## Optimization Strategies

### 1. Lazy Imports

Move imports inside functions to defer loading:

```python
# Before (eager)
from griptape.structures import Agent

def create_agent():
    return Agent()

# After (lazy)
def create_agent():
    from griptape.structures import Agent
    return Agent()
```

### 2. Conditional Imports

Only import heavy modules when actually needed:

```python
def get_config_manager():
    from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
    return GriptapeNodes.ConfigManager()

# Use in functions instead of module level
config_manager = get_config_manager()  # Called when needed
```

### 3. TYPE_CHECKING

Use TYPE_CHECKING for type hints without runtime imports:

```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from griptape.artifacts import BaseArtifact

def process(artifact: "BaseArtifact"):  # Quotes defer evaluation
    ...
```

## Comparing Profiles

To compare before/after optimizations:

```bash
# Before optimization
make profile ARGS="--version"
cp profiles/startup_profile_*.json profiles/before.json

# Make your changes...

# After optimization
make profile ARGS="--version"
cp profiles/startup_profile_*.json profiles/after.json

# Compare
python analyze_profile.py profiles/before.json profiles/after.json
```

## Recent Optimizations

### 2024-12-29: Lazy Griptape Imports

**Changes:**
- Made `base_events.py` griptape imports lazy (moved inside serialization methods)
- Made `config.py` config_manager creation lazy
- Made CLI command imports lazy where possible

**Results:**
- 72% reduction in griptape import time (6.9s → 1.9s)
- Major modules optimized:
  - `griptape.structures.agent`: 434ms → 56ms (87% faster)
  - `griptape.tasks`: 433ms → 55ms (87% faster)
  - `griptape.tools`: 411ms → 37ms (91% faster)
  - `griptape.loaders`: 350ms → 6ms (98% faster)
  - `griptape.drivers`: 343ms → 0.3ms (99.9% faster)

## Troubleshooting

### Profile not generated

Ensure `GRIPTAPE_NODES_PROFILE=1` is set:

```bash
GRIPTAPE_NODES_PROFILE=1 uv run griptape-nodes --version
```

### Import times seem inflated

The profiler tracks cumulative time, so parent modules include time for all child imports. Focus on leaf modules for actual optimization targets.

### Profile directory missing

The `profiles/` directory is created automatically. If it's missing, ensure you have write permissions in the current directory.
