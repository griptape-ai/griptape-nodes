# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

All development commands use the Makefile:

**Development workflow:**

```bash
make install          # Install all dependencies (core + dev + test + docs)
make run               # Run the engine locally (--no-update flag)
make run/watch         # Run engine in watch mode for development
```

**Testing:**

```bash
make test              # Run all tests (unit, integration, workflow)
make test/unit         # Run unit tests only
make test/integration  # Run integration tests only
make test/workflows    # Run workflow tests only
```

**Code quality:**

```bash
make check             # Run all checks (format, lint, types, spell)
make lint              # Run ruff linting with auto-fix
make format            # Format code with ruff + mdformat
make fix               # Format + unsafe ruff fixes (excludes libraries/tests)
```

**IMPORTANT - AI Agent Linting Workflow:**

Claude Code must follow this pattern to prevent lint debt accumulation:

1. **After completing a logical group of changes** (e.g., implementing a feature, fixing a bug)
1. **Run lint check**: `make check`
1. **Fix any issues found** before moving to next major task. Ask the user if they are comfortable running `make fix` (which will make all changes for them) or if they want to step through them one by one.
1. **Always check before completing work sessions**

**Goal: Zero lint errors, always.** Never let lint issues accumulate for "later cleanup."

```bash
# Check specific files/directories:
uv run ruff check path/to/file.py
uv run ruff check libraries/griptape_nodes_neo4j_library/

# Auto-fix simple issues:
uv run ruff check --fix path/to/file.py

# Quick status check:
uv run ruff check --statistics
```

**Documentation:**

```bash
make docs              # Build documentation with mkdocs
make docs/serve        # Serve docs locally for development
```

**Version management:**

```bash
make version/patch     # Bump patch version
make version/minor     # Bump minor version 
make version/major     # Bump major version
make version/publish   # Create and push git tags
```

Single test execution: `uv run pytest tests/path/to/test.py::test_function`

## Architecture Overview

**Core Engine Architecture:**

- `src/griptape_nodes/` - Main engine package
- `src/griptape_nodes/retained_mode/` - Core retained mode API system
- `src/griptape_nodes/app/` - FastAPI application and WebSocket handling
- `src/griptape_nodes/node_library/` - Node library registration system

**Node Library System:**

- Libraries are defined by JSON schema files (`griptape_nodes_library.json`)
- Each library contains node definitions with metadata, categories, and file paths
- Libraries are registered via `LibraryRegistry` singleton
- Node creation flows through `LibraryRegistry.create_node()` -> `Library.create_node()`
- Libraries can define dependencies, settings, and workflows

**Event-Driven Communication:**

- All operations flow through event requests/responses in `retained_mode/events/`
- Event types: `node_events`, `flow_events`, `execution_events`, `config_events`, etc.
- Events are handled by `GriptapeNodes.handle_request()` singleton
- Real-time communication via WebSockets through `NodesApiSocketManager`

**Execution Model:**

- Flows contain multiple nodes with parameter connections
- Execution state managed by `FlowManager` and `NodeManager`
- Supports step-by-step debugging and flow control
- Node resolution and validation before execution

**Storage Architecture:**

- Configurable storage backends: local filesystem or Griptape Cloud
- Static file serving via FastAPI for media assets
- Workspace directory contains flows, configurations, and generated assets

**Retained Mode API:**
The `RetainedMode` class in `retained_mode/retained_mode.py` provides the scriptable Python interface for:

- Flow management: `create_flow()`, `run_flow()`, `single_step()`
- Node operations: `create_node()`, `set_value()`, `get_value()`, `connect()`
- Library introspection: `get_available_libraries()`, `get_node_types_in_library()`
- Configuration: `get_config_value()`, `set_config_value()`

**Key Patterns:**

- All managers are singletons accessed via `GriptapeNodes.ManagerName()`
- Node parameters support indexed access (e.g., `node.param[0][1]`)
- Execution chains can be created with `exec_chain()` helper
- Metadata flows from library definitions to runtime node instances

## Node Development

**Creating Custom Nodes:**

1. Extend `BaseNode` from `exe_types/node_types.py`
1. Define in library JSON with category, metadata, and file path
1. Register library through bootstrap system
1. Nodes automatically inherit parameter system and execution framework

**Library Registration:**

- Default library: `libraries/griptape_nodes_library/`
- Advanced library: `libraries/griptape_nodes_advanced_media_library/`
- Custom libraries registered via config: `app_events.on_app_initialization_complete.libraries_to_register`

**Bootstrap System:**

- `bootstrap/register_libraries_script.py` handles library discovery and registration
- Workflow runners in `bootstrap/workflow_runners/` for different execution contexts
- Structure defined in `bootstrap/structure_config.yaml`

## Profiling (Optional)

**Installation (for advanced users):**

```bash
uv add griptape-nodes[profiling]  # Add profiling extra to existing project
# OR
uv sync --extra profiling         # Sync with profiling extra in development
```

**VS Code Tasks Available:**

- **Find Griptape Nodes Process ID** - Finds running Griptape process PID
- **Attach to Griptape Nodes App: CPU/Memory profiling** - Start profiling (4 variants: with/without sudo, CPU/memory)
- **Stop/Detach Profiling** - Stop profiling sessions (6 variants: with/without sudo, CPU/memory/all)

**Profiling Workflow:**

1. Start Griptape Nodes in debug mode
1. Run "Find Griptape Nodes Process ID" task to get PID
1. Run attach profiling task (use sudo variants on Mac if needed)
1. Exercise your application
1. Run stop/detach task to save profile
1. Profile files saved to `profiles/` with timestamps: `profile_attach_cpu_YYYYMMDD_HHMMSS.mojo`

**Key Points:**

- Austin overwrites existing files - timestamped filenames prevent data loss
- Use detach tasks rather than killing main program for complete data
- Sudo variants required on some systems (especially Mac) for process attachment

# important-instruction-reminders

Do what has been asked; nothing more, nothing less.
NEVER create files unless they're absolutely necessary for achieving your goal.
ALWAYS prefer editing an existing file to creating a new one.
NEVER proactively create documentation files (\*.md) or README files. Only create documentation files if explicitly requested by the User.
