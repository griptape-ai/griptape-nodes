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
- Avoid complex nested expressions - break them into clear, separate statements
- Example: Instead of `value = func() if condition else None`, use:
    ```python
    if condition:
        value = func()
    else:
        value = None
    ```

**CRITICAL: Evaluate ALL failure cases first, success path ONLY at the end** - This is MANDATORY unless explicitly asked otherwise:

- ALL validation checks, error conditions, and failure cases MUST be at the top of the function
- Each failure case should exit immediately (return/raise) with a clear error message
- The success path MUST be at the absolute bottom of the function - never return in the middle
- If there are multiple return statements in the success path, you're probably doing it wrong (unless explicitly requested)
- Bad example:
    ```python
    def process_data(value):
        if value > 0:
            result = calculate(value)
            return result  # SUCCESS IN MIDDLE
        return "Error: value must be positive"  # Failure at end
    ```
- Good example:
    ```python
    def process_data(value):
        if value <= 0:  # FAILURE FIRST
            return "Error: value must be positive"
        if value > 1000:  # MORE FAILURES
            return "Error: value too large"

        # SUCCESS PATH AT END
        result = calculate(value)
        return result
    ```

**CRITICAL: Do NOT use lazy imports** - Imports MUST be at the top of the file:

- ALL imports MUST be at the top of the file in standard order - this is the default and expected pattern
- NEVER use lazy imports (imports inside functions) unless absolutely necessary to resolve a circular import
- If you think you need a lazy import, STOP and explain to the user why you think it's necessary, then ASK for confirmation before proceeding
- The ONLY valid reason for a lazy import is an unavoidable circular import that cannot be resolved through refactoring
- If you must use a lazy import, you MUST add a comment explaining exactly why it's necessary and what circular import it's resolving
- Bad example:
    ```python
    def process_data(value):
        from some_module import helper  # NO! Move to top
        return helper(value)
    ```
- Good example (only if circular import is unavoidable):
    ```python
    def process_data(value):
        # Lazy import required: circular dependency between this module and some_module
        # some_module imports MyClass from this file, and we need helper from some_module
        from some_module import helper
        return helper(value)
    ```

## Exception Handling

**CRITICAL: Only wrap code that actually raises exceptions** - Never add try/except blocks speculatively:

- Before adding exception handling, verify the code actually raises exceptions (check documentation, source code, or type hints)
- Do NOT add try/except blocks "just in case" or because code "might" fail
- Unnecessary exception handling creates misleading code and unnecessary nesting
- If you're unsure whether code raises exceptions, ASK the user first

**Use specific, narrow exception blocks** - Broad exception handling makes debugging impossible:

- Catch ONLY the specific exception types that can be raised (e.g., `FileNotFoundError`, not `Exception`)
- Keep try blocks as small as possible - wrap only the exact line(s) that raise exceptions
- Each distinct operation that can fail should have its own try/except with a specific error message
- Never use bare `except:` or catch `Exception` unless explicitly required
- Bad example:
    ```python
    try:
        data = load_file(path)
        processed = transform_data(data)
        result = save_output(processed)
    except Exception as e:
        return f"Error: {e}"
    ```
- Good example:
    ```python
    try:
        data = load_file(path)
    except FileNotFoundError:
        return f"Error: File not found at {path}"

    try:
        processed = transform_data(data)
    except ValueError as e:
        return f"Error: Invalid data format - {e}"

    try:
        result = save_output(processed)
    except PermissionError:
        return f"Error: Cannot write to output location"
    ```

**Include context in error messages** - Always provide meaningful context to help users understand where errors occur:

- Use the format: **"Attempted to do X. Failed with data Y because of Z."** (X = operation, Y = relevant inputs/identifiers, Z = reason)
- Include `{self.name}` in error messages when available (for classes with a name attribute)
- Include relevant parameter names, object identifiers, or operation context
- This helps users identify which specific node, component, or operation failed
- Bad example:
    ```python
    logger.warning("Invalid input received")
    return "Error: Processing failed"
    ```
- Good example:
    ```python
    logger.warning(f"{self.name} received invalid input: {input_value}")
    return f"Error: {self.name} failed to process input"
    ```
- Good example (structured format):
    ```python
    return f"Attempted to get workflow run command. Failed with workflow_name='{name}' because the workflow was not found in the registry."
    ```

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
