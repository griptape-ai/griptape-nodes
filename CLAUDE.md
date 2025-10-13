# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development

**Commands**

All development commands use the Makefile:

```bash
make check # check linting/formatting/type errors
make fix # fix autofixable errors
```

**Iteration Loop**

When developing, follow this iteration loop:

1. **Make the change**: make the changes required to implement a feature or fix a bug
1. **Run checks**: run `make check` (or `make fix`) to see if any linting/formatting/type errors arose
1. **Fix issues**: resolve all issues from previous step
1. **Continue working**: continue to the next change

## Code Style Preferences

**Avoid Tuples For Return Values** - Tuples should be a last resort. When unavoidable, use NamedTuples for clarity. Prefer separate variables, class instances, or other data structures.

**Simple, Readable Logic Flow** - Prefer simple, easy-to-follow logic over complex nested expressions:

- Use explicit if/else statements instead of ternary operators or nested conditionals
- Put failure cases at the top so the success path flows naturally to the bottom
- Avoid complex nested expressions - break them into clear, separate statements
- Example: Instead of `value = func() if condition else None`, use:
    ```python
    if condition:
        value = func()
    else:
        value = None
    ```

**Avoid Lazy Imports** - Prefer importing modules at the top of the file as a standard practice:

- Put imports at the top of the file in the standard order whenever possible
- Only use lazy imports (imports inside functions) as a last resort when necessary to avoid circular imports or other import-time issues
- This improves readability, makes dependencies clear, and avoids most import-time problems

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
- Griptape Cloud library: `libraries/griptape_cloud/`
- Custom libraries registered via config: `app_events.on_app_initialization_complete.libraries_to_register`
