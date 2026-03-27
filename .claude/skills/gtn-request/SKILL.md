---
name: gtn-request
description: Interact with a running Griptape Nodes engine via the gtn request CLI command. Use when the user wants to discover engines, start sessions, run workflows, or monitor execution.
allowed-tools: Bash(uv:*), Bash(gtn:*)
argument-hint: "[request_type]"
---

# gtn request

Send requests to a running Griptape Nodes engine over WebSocket and print JSON responses. Run via `uv run gtn request`.

## Subcommands

### `uv run gtn request send`

Send a request to the engine.

```
uv run gtn request send <request_type> [--payload JSON] [--engine-id ID] [--session-id ID] [--timeout MS] [--watch]
```

| Argument | Description |
|---|---|
| `request_type` | The request type name (positional, required) |
| `--payload, -p` | JSON string for request fields (default: `"{}"`) |
| `--engine-id, -e` | Target engine ID (sets engine-scoped topics) |
| `--session-id, -s` | Target session ID (sets session-scoped topics) |
| `--timeout, -t` | Timeout in milliseconds (default: 30000) |
| `--watch, -w` | Stream execution events after the initial response (requires `--session-id`) |

### `uv run gtn request list`

List all available request types with their fields and documentation as JSON. Use this to discover what request types exist and what fields they accept.

```bash
uv run gtn request list
```

## Topic Routing

Topics are derived from the arguments to `send`:

- No IDs: broadcast to all engines (`request` / `response`)
- `--engine-id`: engine-scoped (`engines/<id>/request` / `engines/<id>/response`)
- `--session-id`: session-scoped (`sessions/<id>/request` / `sessions/<id>/response`)

## Full Workflow Sequence

Follow these steps in order to discover an engine, start a session, run a workflow, and monitor execution.

### 1. Discover Engines

Send a heartbeat to find available engines. Each running engine responds with its status.

```bash
uv run gtn request send EngineHeartbeatRequest --payload '{"heartbeat_id": "<generate-a-uuid>"}'
```

The response includes `engine_id`, `engine_name`, `session_id` (if one exists), `engine_version`, and `has_active_flow`. Wait ~2 seconds for responses; engines that do not respond are offline. Use the `engine_id` from the response in subsequent commands.

### 2. Start a Session

Establish a session with a specific engine. If a session already exists, it joins the existing one.

```bash
uv run gtn request send AppStartSessionRequest --engine-id <engine_id>
```

The response includes `session_id`. Use this in all subsequent commands.

### 3. List Available Workflows

See which workflows are registered on the engine.

```bash
uv run gtn request send ListAllWorkflowsRequest --session-id <session_id>
```

### 4. Load a Workflow

Load a registered workflow into the engine's execution context.

```bash
uv run gtn request send RunWorkflowFromRegistryRequest --session-id <session_id> \
  --payload '{"workflow_name": "<name>", "run_with_clean_slate": true}'
```

### 5. Get the Top-Level Flow Name

Retrieve the flow name needed to start execution.

```bash
uv run gtn request send GetTopLevelFlowRequest --session-id <session_id>
```

The response includes `flow_name`.

### 6. Start Flow Execution

Start the flow and stream execution events with `--watch`.

```bash
uv run gtn request send StartFlowRequest --session-id <session_id> \
  --payload '{"flow_name": "<flow_name>", "flow_node_name": null, "debug_mode": false}' \
  --watch
```

### 7. End the Session

When finished, release engine resources.

```bash
uv run gtn request send AppEndSessionRequest --engine-id <engine_id>
```

## Watch Mode

When `--watch` is passed, after the initial success response, the command streams execution events as newline-delimited JSON (one JSON object per line) until the flow completes or is cancelled. Session heartbeats are sent automatically every 5 seconds.

### Key Execution Events

| Event | Description |
|---|---|
| `CurrentControlNodeEvent` | A control-flow node is now active |
| `CurrentDataNodeEvent` | A data-processing node is now active |
| `NodeStartProcessEvent` | A node started processing |
| `ParameterValueUpdateEvent` | A parameter value was updated (contains `node_name`, `parameter_name`, `data_type`, `value`) |
| `NodeFinishProcessEvent` | A node finished processing |
| `NodeResolvedEvent` | A node finished and its outputs are available (contains `parameter_output_values`) |
| `ControlFlowResolvedEvent` | The entire flow completed successfully (terminal) |
| `ControlFlowCancelledEvent` | The flow was cancelled or failed (terminal) |

## Output Format

- Success: JSON result printed to stdout, exit code 0
- Failure: JSON error object printed to stderr, exit code 1
- Watch mode: initial result on first line, then one execution event JSON object per line

## Error Handling

- **Timeout**: increase `--timeout` if the engine is slow to respond
- **No API key**: set `GT_CLOUD_API_KEY` in your environment or run `gtn init --api-key <key>`
- **Session expired**: start a new session with `AppStartSessionRequest`
- **Connection failed**: verify the engine is running and you have network access

## Useful Request Types

Use `uv run gtn request list` to see all available types. Common ones:

| Request Type | Scope | Description |
|---|---|---|
| `EngineHeartbeatRequest` | broadcast | Discover running engines |
| `AppStartSessionRequest` | engine | Start or join a session |
| `AppEndSessionRequest` | engine | End a session |
| `SessionHeartbeatRequest` | session | Keep a session alive |
| `ListAllWorkflowsRequest` | session | List registered workflows |
| `RunWorkflowFromRegistryRequest` | session | Load a workflow |
| `GetTopLevelFlowRequest` | session | Get the flow name |
| `StartFlowRequest` | session | Start flow execution |
| `CancelFlowRequest` | session | Cancel a running flow |
| `ListNodesInFlowRequest` | session | List nodes in a flow |
| `ListParametersOnNodeRequest` | session | List parameters on a node |
| `GetParameterValueRequest` | session | Get a parameter's current value |
| `SetParameterValueRequest` | session | Set a parameter's value |
| `ResolveNodeRequest` | session | Execute a single node |
