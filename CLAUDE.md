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

## Following Instructions

**CRITICAL: Do EXACTLY what is requested - NOTHING MORE**
- MANDATORY: If asked for a stub, create ONLY the minimal stub with NO additional fields, parameters, or methods
- MANDATORY: If asked to investigate, ONLY investigate - do NOT implement, design, or plan unless explicitly requested
- MANDATORY: If asked to add one thing, add ONLY that one thing - no "helpful" extras, no "related" additions, no "improvements"
- NEVER add parameters, validation, error handling, or features that weren't explicitly requested
- NEVER anticipate next steps or predict what might be needed
- If the user says "create X", create exactly X - not X plus Y and Z that might be useful
- When in doubt, do LESS - it's better to be told to add more than to overstep

**Examples of OVERSTEPPING (DO NOT DO):**
- User: "Add a name field" -> You add name, validation, and a helper method (WRONG)
- User: "Investigate the macro system" -> You investigate AND create an implementation plan (WRONG)
- User: "Create a stub for GetPreviewRequest" -> You add parameters like max_width, quality, format (WRONG)

**The user will tell you what they want. Wait for them to ask.**

## Code Style Preferences

**Avoid Tuples For Return Values** - Tuples should be a last resort. When unavoidable, use NamedTuples for clarity. Prefer separate variables, class instances, or other data structures.

**Simple, Readable Logic Flow** - Prefer simple, easy-to-follow logic over complex nested expressions. Use explicit if/else statements instead of ternary operators or nested conditionals. Break complex nested expressions into clear, separate statements.

**Evaluate ALL failure cases first, success path ONLY at the end** - ALL validation checks, error conditions, and failure cases must be at the top of the function. Each failure case should exit immediately (return/raise). The success path must be at the absolute bottom of the function.

**Do NOT use lazy imports** - All imports must be at the top of the file. Never import inside functions unless it is the only way to resolve a circular import. If a lazy import is required, add a comment explaining which circular dependency makes it necessary.

**Class organization order** - Organize class members in this order:

1. Class attributes
1. `__init__`
1. Other dunder methods
1. Properties
1. Public instance methods
1. Private instance methods
1. Class methods
1. Static methods

Instance methods come first because they can call anything. Class methods come next because they can only call class/static methods. Static methods come last because they can't call other class methods. Within each group, put high-level methods first and helper methods below the callers that use them.

## Exception Handling

**Only wrap code that actually raises exceptions** - Verify that code raises exceptions before adding try/except. Do not add try/except blocks speculatively. If unsure, ask first.

**Use specific, narrow exception blocks** - Catch only the specific exception types that can be raised. Keep try blocks as small as possible — wrap only the exact lines that raise. Never use bare `except:` or catch `Exception` unless explicitly required.

**Include context in error messages** - Use the format: "Attempted to do X. Failed with data Y because of Z." Include `{self.name}` when available. Include relevant parameter names and operation context.

## Architecture

**Singleton managers** - `GriptapeNodes` is a singleton holding 25+ managers (e.g., `FlowManager`, `NodeManager`), each accessed via `GriptapeNodes.ManagerName()` classmethods.

**Event-driven operations** - All operations flow through request/response event dataclasses defined in `retained_mode/events/`, routed by `GriptapeNodes.handle_request()`.

**Library registration flow** - Libraries are defined by `griptape_nodes_library.json` files and registered via the `LibraryRegistry` singleton. Node creation flows through `LibraryRegistry.create_node()` -> `Library.create_node()`.

**Custom nodes** - Extend `BaseNode` from `exe_types/node_types.py`. Parameters, flows, and connections are defined in `exe_types/core_types.py` and `exe_types/node_types.py`.
