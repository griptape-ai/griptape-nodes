---
name: griptape-nodes-mcp
description: Build, run, and inspect griptape-nodes workflows through the griptape-nodes MCP server. Use when the user asks to construct a node workflow, run an existing one, set parameter values, wire connections between nodes, or read output from a workflow run. Triggers include "build a workflow", "add a node to the flow", "connect these nodes", "run the flow", "what does node X output", and any task involving the `griptape_nodes_*` MCP tools.
---

# Griptape Nodes MCP: Workflow Construction Guide

This skill covers the full cold-start cycle (build → wire → run → read) against the griptape-nodes MCP server, plus the idioms and gotchas discovered from running real workflows.

## Mental Model

- **Workflow**: Top-level namespace. Only ONE can be active at a time. Reset with `ClearAllObjectStateRequest`.
- **Flow**: The canvas inside a workflow. A workflow has exactly one top-level "canvas" flow. Sub-flows are possible but rarely needed for scratch work.
- **Node**: A unit of work with parameters (inputs, outputs, properties).
- **Connection**: An edge between two parameters. Two kinds:
  - **Data flow**: A typed parameter on one node → a typed parameter on another. The engine derives execution order from data dependencies, so data connections alone are usually sufficient.
  - **Control flow**: `exec_out` → `exec_in`. Only needed when two nodes must run in a specific order but don't share data (e.g. side-effecting steps, branching). Skip these by default.
- **Current Context**: A stack (workflow → flow → node). Most requests default to "current" when a name is omitted.

## Survey the Workspace First

Before building anything, find out what is actually loaded in this engine. The set of
registered libraries and the node types they expose is the catalog every later step
draws from, so spend the round trips up front instead of guessing names that may not
exist (or that exist in a different library than you expect).

### Find the workspace directory on disk

The MCP surface does not currently expose the engine's configured workspace path, so
resolve it by shelling out to the `gtn` CLI before doing anything else. The workspace
holds the sandbox library directory (where `RegisterSandboxNodeFromSourceRequest`
writes its `.py` files) and any locally-registered library JSONs the engine pulls in
on startup, so knowing it lets you read library sources and verify sandbox writes:

```
$ gtn config show workspace_directory
~/Projects/griptape/griptape-nodes/GriptapeNodes/

$ gtn config show sandbox_library_directory
sandbox_library
```

- `workspace_directory` is the absolute (or `~`-prefixed) workspace root.
- `sandbox_library_directory` is the sandbox subdirectory **relative to the
  workspace**. The absolute sandbox path is therefore
  `<workspace_directory>/<sandbox_library_directory>` (e.g.
  `~/Projects/.../GriptapeNodes/sandbox_library`).
- The same config file lists `app_events.on_app_initialization_complete.libraries_to_register`,
  i.e. absolute paths to every locally-registered `griptape_nodes_library.json`. If
  you need to inspect a library's source layout (e.g. to read an existing node's
  Python module before writing a similar sandbox node), `gtn config list` points at
  the user config file and the `libraries_to_register` array points at each library
  root.

Do this once per session and remember the paths; they don't change mid-run.

### Survey the registered libraries via MCP

```
A. griptape_nodes_ListRegisteredLibrariesRequest()
   → list of library names currently loaded (e.g. "Griptape Nodes Library",
     "Sandbox Library"). If a library you expect is missing, no `DescribeNodeType`
     call against its node types will resolve.

B. griptape_nodes_ListNodeTypesInLibraryRequest(library="<name>")
   → call once per library you might pull from. The returned node-type names are the
     exact strings to pass to `CreateNodeRequest.node_type` and
     `DescribeNodeTypeRequest.node_type`.

C. (optional) griptape_nodes_ListCategoriesInLibraryRequest(library="<name>")
   → useful when you only care about a slice of a large library (e.g. only image
     nodes) and want to scope the next step.
```

Do this once per session, then reuse the catalog. Skip the survey only when you
already know (from a prior call in the same session) which library provides each node
type you intend to use.

## Canonical Cold-Start Recipe (9 calls after the survey)

For a typical 3-node linear pipeline (e.g. `TextInput → Agent → DisplayText`), once
the workspace survey above has confirmed the relevant library exposes those node
types:

```
1. griptape_nodes_EnsureWorkflowAndFlowRequest()
   → returns workflow_name + flow_name, creates both if missing

2. griptape_nodes_DescribeNodeTypeRequest(node_type="TextInput")
3. griptape_nodes_DescribeNodeTypeRequest(node_type="Agent")
4. griptape_nodes_DescribeNodeTypeRequest(node_type="DisplayText")
   → get exact parameter names/types/modes. Look for:
     - data input(s) (mode_allowed_input == true)
     - data output(s) (mode_allowed_output == true)
     - control params (type == "parametercontroltype"): exec_in / exec_out
       are usually skippable (see Mental Model)

5. griptape_nodes_CreateNodesRequest(nodes=[
       NodeSpec(node_type="TextInput",   parameter_values={"text": "..."}),
       NodeSpec(node_type="Agent"),
       NodeSpec(node_type="DisplayText"),
   ])
   → returns outcomes[]. Read outcomes[i].node_name for the assigned names;
     the engine typically returns "<DisplayName>_1" etc.

6. griptape_nodes_CreateConnectionsRequest(connections=[
       ConnectionSpec(source="TextInput_1", source_param="text",
                      target="Agent_1",     target_param="prompt"),
       ConnectionSpec(source="Agent_1",     source_param="output",
                      target="DisplayText_1", target_param="text"),
   ])
   → data connections only; the engine orders execution from data dependencies.
     Inspect outcomes[]; created_count should equal the number submitted.

7. griptape_nodes_AutoLayoutFlowRequest()
   → required after any multi-node build. Without it, every node lands at
     (0, 0) and the canvas shows them stacked on top of each other. Topologically
     sorts the graph and assigns column-and-row positions. Omit `flow_name` to
     lay out the current-context flow.

8. griptape_nodes_StartFlowRequest(wait_for_completion=True, completion_timeout_ms=60000)
   → omit flow_name; the handler uses the current-context flow.
     wait_for_completion blocks until the flow resolves or times out.

9. griptape_nodes_GetParameterValueRequest(node_name="DisplayText_1", parameter_name="text")
   → the terminal node's output.
```

## Key Idioms

- **Survey the workspace before picking node types.** Resolve the workspace directory on disk with `gtn config show workspace_directory` (and `gtn config show sandbox_library_directory` for the sandbox subpath) so you know where sandbox `.py` files land and where local library JSONs live. Then run `ListRegisteredLibrariesRequest` and `ListNodeTypesInLibraryRequest` for the libraries you care about before reaching for `DescribeNodeType`. The catalog tells you which node types actually exist in this engine and which library owns each one, which is the input both `DescribeNodeTypeRequest.library` and `CreateNodeRequest.specific_library_name` expect when the same name lives in more than one library.
- **Discover before wiring.** Always call `DescribeNodeType` for each node type you intend to use before guessing parameter names. The cost is 3-5 calls up front but saves many round trips fighting typos and assumed-wrong names.
- **Wire data, not control.** The engine derives execution order from data dependencies, so `exec_out` → `exec_in` connections are usually noise. Only add them when two nodes must run in a specific order but don't exchange data.
- **Always run AutoLayout after a multi-node build.** Without it nodes land at (0, 0) and stack on top of each other. `AutoLayoutFlowRequest` is one round trip and idempotent; treat it as the closing step of any build phase.
- **Batch whenever possible.** Prefer `CreateNodesRequest` + `CreateConnectionsRequest` over their single-entry siblings. Each batch call is one round trip regardless of payload size, and the engine validates the whole batch together.
- **Inline parameter values in `CreateNodesRequest`.** `NodeSpec.parameter_values` is applied right after node creation, so one call replaces N `SetParameterValue` calls.
- **Use `wait_for_completion=True` on `StartFlowRequest`.** For workflows that touch LLMs, image generators, or long I/O, set `completion_timeout_ms` generously (60000+ ms). Otherwise the call returns the instant the flow is kicked off and you have to poll.
- **Omit `flow_name` on `StartFlowRequest`** when you just finished building a single flow. The handler defaults to the current-context flow.
- **Read responses, don't assume.** `CreateNodesRequest.outcomes[i].node_name` and `CreateNodesRequest.outcomes[i].parameter_assignments` tell you exactly what landed.

## Response Shape

Every MCP tool returns a trimmed object:

```json
{
  "ok": true,
  "details": "<human-readable summary>",
  "altered_workflow_state": true|false,
  "...": "...payload fields..."
}
```

`ok` is always true on reachable responses. Failures surface as tool errors (pi prints them as `Error:` messages); read the error for the reason.

## Gotchas

### DescribeNodeType may be partial

`DescribeNodeType` probes by instantiating the node class. For node types whose `__init__` performs I/O (network, auth, disk), instantiation may fail. When that happens the response still succeeds but returns:

- Full library-level `metadata` (category, description, display_name, etc.)
- `parameters: []` (empty — instantiation failed before parameters were declared)
- `probe_error: "<exception type>: <message>"`

In that case you still know what the node does, but you cannot see its parameter schema from MCP alone. Consider falling back to a different node type, or describe on a system where credentials are present.

### CreateNode can silently produce an ErrorProxyNode

When a node fails to instantiate and `create_error_proxy_on_failure=True` (the default), the engine substitutes an `ErrorProxyNode` and reports success. Inspect the outcome's `node_type` (if present) or the `details` string if a later step fails mysteriously. If you need strict failure semantics, set `create_error_proxy_on_failure=False` on the spec.

### Default node names contain spaces

The engine names nodes after `metadata.display_name`, which is often human-readable with spaces (e.g. `"Text Input"`, `"Display Text"`). That works for every API, but it's easy to typo. Either pass an explicit `node_name` per spec, or always read the returned `outcomes[i].node_name` and reuse it verbatim.

### `MathExpression` uses a..z variables

`MathExpression` exposes 26 variables `a` through `z`, all as parameters. `num_variables` (a slider 1-26) controls how many are surfaced in the UI via `ui_options.hide`. To use variable `e`, set `num_variables >= 5`, then set `e`'s value.

### `AddTextToImage` vs `AddTextToExistingImage`

- `AddTextToImage` (`group: "create"`) **generates a new image**. It has `width`, `height`, `background_color` and **no** `input_image`.
- `AddTextToExistingImage` (`group: "edit"`) **overlays text on an existing image**. It has `input_image`, `template_values`, alignment, margin, and hexa (alpha) colors.

Name alone does not make this clear. Read the `description` in DescribeNodeType's `metadata`.

### Only one workflow in context at a time

`SetWorkflowContextRequest` refuses if a workflow is already in context. To swap, `ClearAllObjectStateRequest(i_know_what_im_doing=True)` first — this wipes EVERYTHING (nodes, flows, connections, workflow). There is no softer reset today.

### Agents cannot be interrupted mid-run

There is no pause/cancel for a running flow today. Use `completion_timeout_ms` to bound the wait; if the timeout fires, `StartFlowRequest` returns a failure but the flow keeps running in the engine until it finishes or errors. A subsequent `StartFlowRequest` will fail with "Flow is already running" until it does.

## Tool Cheat Sheet

| Goal | Tool |
|------|------|
| Bootstrap a workflow + flow from cold | `EnsureWorkflowAndFlowRequest` |
| Discover libraries / node types | `ListRegisteredLibrariesRequest`, `ListNodeTypesInLibraryRequest` |
| Inspect a node type's parameters | `DescribeNodeTypeRequest` |
| Create one or many nodes (with initial params) | `CreateNodeRequest` / `CreateNodesRequest` |
| Wire one or many edges | `CreateConnectionRequest` / `CreateConnectionsRequest` |
| Lay out the canvas after a multi-node build | `AutoLayoutFlowRequest` |
| Move a single node to an explicit position | `SetNodeMetadataRequest` (set `metadata.position`) |
| Set a parameter after creation | `SetParameterValueRequest` |
| Read a parameter | `GetParameterValueRequest` |
| Run synchronously | `StartFlowRequest(wait_for_completion=True, completion_timeout_ms=...)` |
| Run from a specific node | `StartFlowFromNodeRequest` |
| Resolve a single node without firing the control flow | `ResolveNodeRequest` |
| Rename a node or flow | `RenameObjectRequest(allow_next_closest_name_available=True)` |
| Lock or unlock a node | `SetLockNodeStateRequest` |
| Inspect state | `ListNodesInFlowRequest`, `ListConnectionsForNodeRequest`, `GetNodeResolutionStateRequest` |
| Register a sandbox node type from Python source | `RegisterSandboxNodeFromSourceRequest` (see Custom nodes below) |
| Reset everything | `ClearAllObjectStateRequest(i_know_what_im_doing=True)` |

## Custom nodes

If the task involves writing a new node type via `RegisterSandboxNodeFromSourceRequest`, read [`docs/developing_nodes/comprehensive_guide.md`](../../../docs/developing_nodes/comprehensive_guide.md) **before** drafting source. The guide documents the engine-side conventions a sandbox class must follow:

- `BaseNode` subclassing and the `process` / `aprocess` contract
- `Parameter` declaration, modes (`mode_allowed_input` / `..._property` / `..._output`), traits
- `ParameterString` / `ParameterImage` / etc. helpers (preferred over hand-rolled `Parameter`)
- `ParameterGroup` / `ParameterList` containers
- Connection rules and node states

`RegisterSandboxNodeFromSourceRequest` executes the source inside the engine process with no isolation, so matching the conventions up front is faster than iterating on registration failures. For pure workflow-driving tasks (build → wire → run → read) the guide is overkill — stick to this skill.

## Example: One-Shot Haiku Pipeline

Goal: run an `Agent` on a one-line prompt and read the output.

1. `EnsureWorkflowAndFlowRequest()`
2. `DescribeNodeTypeRequest(node_type="TextInput")` → text output parameter is `text`
3. `DescribeNodeTypeRequest(node_type="Agent")` → inputs `prompt`; outputs `output`
4. `DescribeNodeTypeRequest(node_type="DisplayText")` → input `text`
5. `CreateNodesRequest` with 3 specs, TextInput's `text` set inline to the prompt
6. `CreateConnectionsRequest` with 2 specs (data only: `text`→`prompt`, `output`→`text`)
7. `AutoLayoutFlowRequest()` → arrange the 3 nodes across columns
8. `StartFlowRequest(wait_for_completion=True, completion_timeout_ms=60000)`
9. `GetParameterValueRequest(node_name="DisplayText_1", parameter_name="text")`

Total: 9 MCP calls from empty engine to rendered output.
