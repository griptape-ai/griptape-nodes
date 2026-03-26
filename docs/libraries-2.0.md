# Libraries 2.0: Process-Isolated Library Architecture

## Background

Libraries currently run in the same process as the engine. Every node class directly calls into `GriptapeNodes` singleton managers, holds live Python references to other nodes, and passes arbitrary Python objects between connected nodes via shared memory.

This deep coupling has several consequences:

- A crashing library takes down the entire engine
- Libraries with conflicting Python dependencies cannot coexist without workarounds (partially mitigated by per-library venvs, but `sys.path` is still shared)
- Untrusted library code has unrestricted access to engine internals, secrets, and other libraries' data
- Libraries cannot be updated or restarted independently of the engine

Libraries 2.0 moves each library into its own child process. Each library gets an isolated Python environment, fault boundaries, and a defined IPC interface to the engine.

______________________________________________________________________

## Goals

1. **Fault isolation** — a crashing library does not affect the engine or other libraries
1. **Full dependency isolation** — libraries with conflicting deps coexist without `sys.path` conflicts
1. **Security sandboxing** — untrusted library code cannot access engine internals
1. **Hot-reload** — update or restart a library without restarting the engine

______________________________________________________________________

## Process Model

```
Engine Process (parent / orchestrator)
  |- LibraryProcessManager
  |    |- LibraryProcessHandle("standard_library")   -> child process 1
  |    |- LibraryProcessHandle("advanced_media")     -> child process 2
  |    |- LibraryProcessHandle("community_lib")      -> child process 3
  |
  |- ParallelResolutionMachine (DAG scheduling)
  |- Connection topology (node names, param names — no live node instances)
  |- Node registry (node name -> type, owning library, parameter schemas)
  |- Serialized output cache (completed outputs awaiting downstream routing)
  |- GriptapeNodes singleton (config, secrets, session, project state)
```

```
Library Child Process (one per library)
  |- GriptapeNodes singleton (full — all managers initialized)
  |- Live BaseNode instances for this library's nodes
  |- parameter_values / parameter_output_values on each node
  |- Library's full venv and imported modules
```

### State Split

**Parent (orchestrator) owns:**

- `Connection` objects — node names, param names, connection IDs. No live `BaseNode` references.
- Node registry — for each node: type, owning library/child process, parameter schemas. Metadata only; the parent never holds a live node instance for a remote library.
- DAG state — ready / running / completed / errored per node. `ParallelResolutionMachine` runs here.
- Serialized output cache — when a node completes, its serialized `parameter_output_values` are stored so they can be forwarded to downstream nodes (possibly in a different child).
- Library process handles — PID, transport connection, health status.
- Config/secrets (source of truth), session, project, user state.

**Child (engine) owns:**

- Live `BaseNode` instances with `parameter_values` / `parameter_output_values`.
- `ObjectManager` / `NodeManager` scoped to this library's nodes.
- `EventManager` — local event routing, plus forwarding to parent for UI broadcast.
- Library's Python modules and venv.
- Config/secrets — a synced copy, pushed by parent at startup and on change.

**Request routing:**

- Requests originating from the UI reach the parent, which routes them to the appropriate child based on node ownership.
- Requests originating from within node code (e.g., a node calling `GriptapeNodes.handle_request()`) are processed locally by the child's own `GriptapeNodes` singleton. The child's managers handle these directly.
- Cross-library direct node references are disallowed. Data flows between libraries only via connections, mediated by the parent's serialized output cache.

### Library Lifecycle

Extends the existing `LibraryManager` state machine with a new terminal state:

```
DISCOVERED -> METADATA_LOADED -> EVALUATED -> DEPENDENCIES_INSTALLED -> LOADED -> PROCESS_STARTED
```

After LOADED, `LibraryProcessManager` spawns a child process using the library's per-library venv Python interpreter. The child runs `library_worker.py`, which bootstraps a full `GriptapeNodes` singleton and connects back to the parent via IPC.

### Health Checking and Restart

- Heartbeat ping/pong every 5 seconds. Three missed heartbeats triggers restart.
- On crash: mark all library nodes as ERRORED, cancel in-flight executions, respawn the process, replay node creation commands from parent metadata.
- Graceful shutdown: drain in-flight work (with configurable timeout), then SIGTERM, then SIGKILL.

### Hot-Reload

1. Send `prepare_shutdown` to library process, drain in-flight work
1. Kill old process, re-run dependency install (`uv`)
1. Re-register library in `LibraryRegistry`, spawn fresh process
1. Replay node creation and connection commands from parent metadata

Hot-reload is feasible because the parent is the source of truth for all structural state (topology, node registry). The library child process is stateless between node executions.

______________________________________________________________________

## IPC Protocol

### Transport Abstraction

Rather than hardcoding a single IPC mechanism, a transport interface allows multiple backends. The existing `Client` class (`api_client/client.py`) is currently hardcoded to WebSocket; Libraries 2.0 extracts the transport concern into an interface:

```python
class Transport(ABC):
    async def send(self, message: bytes) -> None: ...
    async def recv(self) -> bytes: ...
    async def close(self) -> None: ...

class TransportServer(ABC):
    async def accept(self) -> Transport: ...
    async def close(self) -> None: ...
```

Two backends:

- **`UnixSocketTransport`** — Unix domain sockets (named pipes on Windows). Sub-millisecond latency for local processes. Length-prefixed framing: `[4-byte message length][message bytes]`. Socket path: `/tmp/griptape_nodes/<session_id>/<library_name>.sock`.
- **`WebSocketTransport`** — reuses the existing `SubprocessWebSocketSenderMixin` / `SubprocessWebSocketListenerMixin` infrastructure. Works across machines; enables future remote library deployment.

### Request-Response Correlation

`RequestClient` (`api_client/request_client.py`) already provides request-response semantics on top of pub/sub messaging: it generates `request_id`s, tracks pending requests with `asyncio.Future`s, supports timeouts, and matches responses to requests. This infrastructure is reused for IPC — `RequestClient` wraps a `Client` backed by the chosen transport, and the same `request()` / `_resolve_request()` / `_reject_request()` machinery handles correlation.

### Message Envelope

```json
{
  "message_id": "uuid-string",
  "message_type": "execute_node",
  "payload": { ... }
}
```

Serialized as JSON. `message_id` is a UUID generated by `RequestClient` for request-response correlation. The protocol is fully async — multiple requests can be in-flight simultaneously.

Payloads use the existing `BaseEvent.json()` / `deserialize_event()` / `PayloadRegistry` infrastructure, which already handles round-trip serialization over WebSocket.

### Message Types

**Parent -> Child:** `create_node`, `destroy_node`, `execute_node` (includes serialized input values), `cancel_node`, `sync_config`, `connection_callback`, `heartbeat_ping`, `shutdown`, `prepare_shutdown`

**Child -> Parent:** `execution_complete` (includes serialized output values), `execution_error`, `event_broadcast`, `heartbeat_pong`

______________________________________________________________________

## Serialization

### Approach

Parameter values crossing process boundaries are serialized to JSON using the existing infrastructure:

- **Primitives** (`str`, `int`, `float`, `bool`, `None`, `list`, `dict`): direct JSON encoding.
- **Griptape artifacts** (`ImageArtifact`, `TextArtifact`, `AudioArtifact`, etc.): `SerializableMixin.to_dict()` already base64-encodes binary content. Roundtrip deserialization must be audited and fixed where `from_dict()` is missing.
- **Pydantic models**: `model_dump()` / `model_validate()` with a type tag: `{"__type__": "fully.qualified.ClassName", "__data__": {...}}`.
- **Events and payloads**: existing `BaseEvent.json()` / `deserialize_event()` / `PayloadRegistry`.

**Design principle:** The serializer must fail loudly when it cannot roundtrip a value, rather than silently degrading to `str()`. This fixes the existing pattern in `default_json_encoder` and `TypeValidator.safe_serialize()` where unserializable objects become opaque strings.

### Binary Data

Binary data (images, audio) is never sent directly over the IPC wire. Instead, nodes use `StaticFilesManager.save_static_file()` to write binary content to storage (local filesystem or Griptape Cloud) and produce a download URL. Only the URL crosses process boundaries — it is a small JSON string regardless of the underlying data size.

The existing `StaticFilesManager` (`retained_mode/managers/static_files_manager.py`) already supports this pattern:

- `CreateStaticFileUploadUrlRequest` / `CreateStaticFileDownloadUrlRequest` generate presigned URLs for upload/download
- `save_static_file()` writes bytes to the workspace and returns a URL
- Both local (`LocalStorageDriver`) and cloud (`GriptapeCloudStorageDriver`) backends are supported

When a node in a child process produces an image or audio artifact, it saves the binary content via `StaticFilesManager` (which runs locally in the child) and passes the resulting URL as the output parameter value. Downstream nodes (even in different library processes) receive only the URL and can fetch the data on demand.

No pickle. All serialization goes through JSON. If a value cannot be serialized, it must fail loudly rather than falling back to pickle or `str()`.

______________________________________________________________________

## Config/Secrets Synchronization

The child has a real `ConfigManager` and `SecretsManager`, but the parent is the source of truth since it loads config files and receives user-supplied secrets.

**At startup:** Parent sends a `sync_config` message containing the full config state and secrets. The child initializes its `ConfigManager` / `SecretsManager` from this data rather than reading from disk.

**On change:** When the parent's config changes (file watcher, user action), it sends an updated `sync_config` to all running children.

The child inherits the parent's environment variables by default, so `GTN_CONFIG_*` env vars are available automatically.

______________________________________________________________________

## Node Execution Flow

### Current (in-process)

```
ParallelResolutionMachine
  -> collect_values_from_upstream_nodes()  [shared memory read]
  -> NodeExecutor.execute(node)
     -> node.aprocess()                    [in-process]
  -> read parameter_output_values          [shared memory read]
```

### Libraries 2.0

```
ParallelResolutionMachine (parent)
  -> find ready nodes in DAG
  -> look up upstream connections in topology
  -> pull serialized outputs from cache for upstream nodes
  -> IPC: execute_node(node_name, {param: serialized_value, ...}) -> child
     -> child: deserialize inputs
     -> child: set inputs on node via local handle_request()
     -> child: node.aprocess()
     -> child: serialize parameter_output_values
  -> IPC: execution_complete(serialized_outputs) -> parent
  -> parent: store in serialized output cache, advance DAG
```

### Cross-Library Data Flow

When Node A (library X) connects to Node B (library Y):

1. Node A executes in library X's child. Outputs serialized and sent to parent via `execution_complete`.
1. Parent caches serialized outputs.
1. When Node B is scheduled, parent retrieves cached outputs from step 2 and sends them to library Y's child in the `execute_node` message.
1. Library Y's child deserializes and injects into Node B.

For same-library connections, the parent follows the same path (parent intermediates all data flow). This keeps the parent as the single source of truth for all node output values and simplifies the implementation. Per-library optimization (direct same-process data flow) can be added later.

### The `RemoteNodeExecutor`

`NodeExecutor` gains a remote execution path. When the node's owning library runs in a child process, `NodeExecutor` dispatches to `RemoteNodeExecutor`, which sends the `execute_node` IPC command and awaits `execution_complete`. When running in debug/in-process mode, `NodeExecutor` falls through to the existing `node.aprocess()` path.

All libraries run out-of-process by default. The in-process path is available only via a debug flag for library developers.

______________________________________________________________________

## Nodes That Will Break

### What is No Longer an Issue

With a full `GriptapeNodes` singleton running in the child, the majority of coupling patterns are handled transparently:

| Pattern                                             | Why it's no longer an issue                                         |
| --------------------------------------------------- | ------------------------------------------------------------------- |
| Config/Secrets reads                                | Real managers in child, synced from parent                          |
| Event emission (`put_event`)                        | Real `EventManager` in child; events forwarded to parent            |
| `handle_request()` for engine commands              | Works natively against child's local singleton                      |
| `FlowManager.get_connections()` (same-library)      | Works against child's local `FlowManager`                           |
| `AsyncResult` generator execution                   | Runs in child's event loop; `to_thread` uses child's loop           |
| `ObjectManager.get_object_by_name()` (same-library) | Returns local object directly                                       |
| Cancellation (`threading.Event`)                    | Local event in child; parent sends `cancel_node` IPC, child sets it |

### Remaining Issues

| Pattern                            | Difficulty | Strategy                                                                                                                                                                                                                                                                                                    |
| ---------------------------------- | ---------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Cross-library node references      | HIGH       | Disallowed. Data flows between libraries only via connections through the parent's cache. `BaseIterativeStartNode.end_node` must always be in the same library.                                                                                                                                             |
| Cross-library connection callbacks | MEDIUM     | `allow_incoming_connection` / `after_outgoing_connection` receive live `BaseNode` instances. For cross-library connections, the remote node is not available locally. A `ConnectionCallbackContext` dataclass provides the same read-only interface (name, type, param schemas) serialized from the parent. |
| `SubflowNodeGroup`                 | HIGH       | See SubflowNodeGroup Rearchitecture below.                                                                                                                                                                                                                                                                  |
| stdout/logging forwarding          | LOW        | Each child has its own stdout. Structured logs must be forwarded to parent via IPC for display.                                                                                                                                                                                                             |

### Constraint

Iterative start/end node pairs (`BaseIterativeStartNode` / `BaseIterativeEndNode`) and node group members must belong to the same library. This is enforced at connection creation time.

### Assumptions That Are No Longer True

| Assumption                                                          | Reality in Libraries 2.0                                                             |
| ------------------------------------------------------------------- | ------------------------------------------------------------------------------------ |
| `parameter_output_values` are instantly visible to downstream nodes | Values are serialized, cached in parent, forwarded to downstream library             |
| `sys.stdout` capture affects engine output                          | stdout is local to the library child; must be forwarded                              |
| All nodes share the same `sys.path`                                 | Each library has its own isolated venv                                               |
| `ObjectManager.get_object_by_name()` always returns a live object   | Returns local object (same library) or fails (cross-library — disallowed)            |
| Connection callbacks receive live `BaseNode` instances              | Cross-library callbacks receive `ConnectionCallbackContext` with serialized metadata |

______________________________________________________________________

## SubflowNodeGroup Rearchitecture

`SubflowNodeGroup` is a `BaseNode` subclass that does engine-level work: creating flows, moving nodes between flows, rewiring connections, executing subflows, and reading child output values via direct calls to `FlowManager`, `NodeManager`, and `ObjectManager`. It is architecturally inverted — orchestration logic lives in a node rather than the engine.

Rather than creating a new manager, this logic is distributed into the components that already own the relevant state:

**`FlowManager` gains:**

- Proxy parameter creation and deletion when nodes are grouped/ungrouped (it already owns connections and auto-detects `is_node_group_internal` on connection creation)
- Connection remapping through proxy parameters when group composition changes
- Subflow creation when a group is formed (it already handles `CreateFlowRequest`)

**`NodeManager` gains:**

- Inlined logic for group add/remove in its existing `AddNodesToNodeGroupRequest` / `RemoveNodeFromNodeGroupRequest` handlers (currently these delegate entirely to `SubflowNodeGroup`)
- Node movement between flows on group operations (via `MoveNodeToNewFlowRequest`, which it already handles)

**`NodeExecutor` keeps:**

- Iteration/while-loop orchestration (`handle_iterative_group_execution()`, `handle_while_group_execution()`) — already there
- Flow packaging (`_package_subflow_group_body()`) and subprocess/cloud execution — already there
- Output value propagation after group execution

**`SubflowNodeGroup` becomes:**

- A thin `BaseNode` subclass with group metadata (`is_node_group`, child node registry)
- Execution environment parameters (`execution_environment` dropdown)
- Iteration/while-specific parameters and state (items, iteration count, control inputs)
- No direct calls to `GriptapeNodes` managers

**Result:** The group node remains a real `BaseNode` in the DAG — it just no longer does engine work itself. The process isolation problem is solved because `SubflowNodeGroup` in a library child process contains only parameters and state; all connection remapping and flow manipulation is handled by the parent's `FlowManager` and `NodeManager`.

______________________________________________________________________

## Additional Challenges

### Startup Time

Spawning a Python process per library adds startup latency proportional to the number of libraries. Mitigate by spawning processes in parallel after the LOADED phase.

### Memory Overhead

Each library process has its own Python interpreter and venv imports. With many libraries loaded simultaneously, this could be significant. Future work: an option to group small or trusted libraries into a shared process.

### Debugging

Stack traces from library process crashes must be forwarded to the engine for display. Breakpoints in node code require attaching a debugger to the specific library child process. A debug flag that runs all libraries in-process (bypassing IPC) is essential for library developers.

### Module Namespace Isolation

Today, `importlib.util.spec_from_file_location()` loads library modules with generated names (`gtn_dynamic_module_<filename>_<hash>`). In separate processes, each library has its own module namespace with no collision risk. The dynamic module naming workaround is no longer necessary.

______________________________________________________________________

## New Components

### New Files

| File                                                                   | Purpose                                                                  |
| ---------------------------------------------------------------------- | ------------------------------------------------------------------------ |
| `src/griptape_nodes/retained_mode/managers/library_process_manager.py` | Process spawning, health checking, restart                               |
| `src/griptape_nodes/bootstrap/library_worker.py`                       | Library process bootstrap (initializes full GriptapeNodes, connects IPC) |
| `src/griptape_nodes/ipc/transport.py`                                  | Abstract `Transport` / `TransportServer` interface                       |
| `src/griptape_nodes/ipc/unix_socket_transport.py`                      | Unix domain socket backend                                               |
| `src/griptape_nodes/ipc/websocket_transport.py`                        | WebSocket backend (reuses existing mixin infrastructure)                 |
| `src/griptape_nodes/ipc/protocol.py`                                   | Message types and envelope format                                        |

### Key Files to Modify

| File                                                             | Change                                                                                                                                                                        |
| ---------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `src/griptape_nodes/common/node_executor.py`                     | Add remote execution path (`RemoteNodeExecutor`) dispatched when node's library is out-of-process                                                                             |
| `src/griptape_nodes/retained_mode/managers/library_manager.py`   | Add `PROCESS_STARTED` lifecycle state                                                                                                                                         |
| `src/griptape_nodes/machines/parallel_resolution.py`             | Integrate with remote execution; serialize/deserialize values at cross-process boundaries; maintain serialized output cache                                                   |
| `src/griptape_nodes/exe_types/node_types.py`                     | `Connection` — use node names, not live refs, for cross-library connections                                                                                                   |
| `src/griptape_nodes/exe_types/base_iterative_nodes.py`           | Enforce same-library constraint for start/end pairs                                                                                                                           |
| `src/griptape_nodes/exe_types/node_groups/subflow_node_group.py` | Strip engine calls; becomes a thin parameter/state holder                                                                                                                     |
| `src/griptape_nodes/retained_mode/managers/flow_manager.py`      | Add proxy parameter creation/deletion and connection remapping for group operations                                                                                           |
| `src/griptape_nodes/retained_mode/managers/node_manager.py`      | Inline group add/remove logic from SubflowNodeGroup into existing request handlers                                                                                            |
| `src/griptape_nodes/retained_mode/events/base_events.py`         | Fix silent serialization fallbacks — fail loudly on unserializable values                                                                                                     |
| `src/griptape_nodes/api_client/client.py`                        | Extract transport abstraction; decouple WebSocket transport from message send/receive interface so `RequestClient` can operate over Unix sockets or WebSocket interchangeably |

______________________________________________________________________

## Implementation Phases

### Phase 1: Transport & Library Worker Bootstrap

- Define `Transport` / `TransportServer` interface
- Implement Unix socket backend with length-prefixed framing
- Build `library_worker.py`: bootstraps full `GriptapeNodes`, loads library, connects IPC
- Build `LibraryProcessManager` + `LibraryProcessHandle`
- Extend `LibraryManager` lifecycle with `PROCESS_STARTED` state
- Define IPC message envelope; implement heartbeat ping/pong
- **Milestone:** Child process starts, handshake completes, heartbeat works.

### Phase 2: Single Node Remote Execution

- Implement `execute_node` / `create_node` / `destroy_node` messages
- Event forwarding pipeline: child `EventManager` -> IPC -> parent event queue -> WebSocket broadcast
- Config/secrets `sync_config` message at startup
- `NodeExecutor` remote dispatch for out-of-process libraries
- **Milestone:** `EchoNode` executes in a child subprocess and returns the correct value. Progress events appear in the UI.

### Phase 3: Full DAG + Cross-Library Data Flow

- Modify `ParallelResolutionMachine.collect_values_from_upstream_nodes()` to serialize/deserialize values at process boundaries
- Parent serialized output cache: store completed outputs, forward to downstream children
- `cancel_node` IPC message
- Binary artifact transfer via `StaticFilesManager` URLs (no binary data over the wire)
- **Milestone:** Chained nodes within one library work. Cross-library data flow works. Binary artifacts (image/audio) transfer via URL without data crossing the IPC wire.

### Phase 4: Connection Callbacks & Node Groups

- `ConnectionCallbackContext` dataclass for cross-library connection callbacks
- `connection_callback` IPC message
- Enforce same-library constraint for iterative node pairs and group members
- Move proxy parameter / connection remapping logic from `SubflowNodeGroup` into `FlowManager`
- Move node movement / group lifecycle logic from `SubflowNodeGroup` into `NodeManager` request handlers
- `SubflowNodeGroup` stripped to a thin parameter/state holder
- **Milestone:** Cross-library connections work with proper validation callbacks. Grouped nodes execute correctly. `SubflowNodeGroup` contains no direct manager calls.

### Phase 5: Lifecycle & Hardening

- Health checking (heartbeat) and automatic restart on crash
- Hot-reload: drain, kill, reinstall deps, respawn, replay node creation
- Graceful shutdown with configurable timeout
- WebSocket transport backend
- Debug flag for in-process execution (library developer experience)
- Forward library process stack traces and structured logs to parent
- **Milestone:** Library crash triggers automatic restart. Hot-reload works. Debug in-process mode works.

______________________________________________________________________

## Testing Strategy

### Overview

The existing test infrastructure (pytest, asyncio strict mode, `isolate_user_config` autouse fixture, strong `Request -> Result` event patterns) provides a good foundation. The key principle is to test as much as possible without a real subprocess, and only cross the process boundary for tests that specifically require it.

One notable gap to be aware of: the existing `SubprocessWorkflowExecutor` has no test coverage. Libraries 2.0 must not repeat this pattern — subprocess communication needs explicit tests from the start.

### Layer 1: Unit Tests (no subprocess)

**Transport abstraction** — test both backends against the same interface:

- In-process socket pair: two coroutines communicating over `socketpair()` — no process spawn needed
- Message framing: serialize/deserialize each message type
- Message ID correlation for request-response matching
- Both `UnixSocketTransport` and `WebSocketTransport` implement the same `Transport` interface; test once, run against both

**Serialization** — the highest-priority unit tests since everything depends on correct serialization:

- Roundtrip tests for every supported type (primitives, Griptape artifacts, Pydantic models)
- Tests that verify loud failures for unserializable types — must raise, not fall back to `str()`
- Verify `ImageArtifact` and `AudioArtifact` outputs produce `StaticFilesManager` URLs, not inline binary data

**`LibraryProcessManager`** — test process lifecycle with a stub subprocess:

- Spawn -> ready signal received -> graceful shutdown sequence
- Three missed heartbeats triggers restart

### Layer 2: Subprocess Integration Tests (real subprocess, test library)

A **test library** at `tests/fixtures/test_library/` contains nodes designed to exercise specific behaviors across process boundaries:

| Node             | What it tests                                                                                     |
| ---------------- | ------------------------------------------------------------------------------------------------- |
| `EchoNode`       | Baseline: input value passes through to output                                                    |
| `ConfigReadNode` | Config sync: reads a config value synced from parent, outputs it                                  |
| `SecretReadNode` | Config sync: reads a secret synced from parent, outputs it                                        |
| `LargeDataNode`  | Binary transfer: produces a large binary artifact saved via `StaticFilesManager`, outputs the URL |
| `SlowNode`       | Cancellation: sleeps N seconds, checks `is_cancellation_requested`                                |
| `CrashNode`      | Fault injection: crashes the process mid-execution                                                |

Key integration tests:

- `EchoNode` executes and returns value — the smoke test milestone for Phase 2
- Two `EchoNode`s chained in the same library — data flows through parent cache within one process
- `EchoNode` (library A) -> `EchoNode` (library B) — cross-library serialization roundtrip
- `LargeDataNode` -> `EchoNode` — URL-based binary transfer (no binary data in IPC messages)
- `CrashNode` execution -> engine detects crash -> library respawns -> nodes marked ERRORED
- `SlowNode` execution -> `cancel_node` IPC command -> node stops cleanly
- Hot-reload: trigger reload, new process starts, executions continue correctly

These tests are slower and should run serially (process management is stateful). Run them in a separate suite: `make test/integration`.

### Layer 3: End-to-End Workflow Tests

Run complete workflows — the kind a user would create — through the full system with libraries out-of-process:

- A workflow with nodes from a single library executes correctly end-to-end
- A workflow with nodes from two different libraries executes correctly end-to-end
- A workflow survives a library crash mid-execution with correct error propagation to the UI

### Development Checkpoints by Phase

| Phase                 | Done when...                                                                                                                                    |
| --------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| 1: Transport & worker | Child starts, handshake completes, heartbeat works. `pytest tests/unit/ipc/` passes for both transport backends.                                |
| 2: Single node        | `EchoNode` completes in subprocess. `ConfigReadNode` and `SecretReadNode` outputs match parent values.                                          |
| 3: Full DAG           | Chained `EchoNode`s produce correct output. `LargeDataNode` URL arrives and is resolvable. Cross-library data flow (lib A -> lib B) works.      |
| 4: Callbacks          | Connection creation triggers `allow_incoming_connection` in the library process and the accept/reject result is honored. Grouped nodes execute. |
| 5: Lifecycle          | `CrashNode` triggers automatic restart. Restarted process accepts new executions. Hot-reload produces a fresh process with updated behavior.    |

### Practical Concerns

**Flakiness:** Subprocess tests are sensitive to startup time. Use event-based waiting with a timeout (not `time.sleep()`) tied to the `PROCESS_STARTED` lifecycle state. Do not begin test assertions until the process signals ready.

**Test isolation:** Each integration test should spawn and tear down its own library processes via a pytest fixture. Do not share processes between tests.

**Observability:** Library processes should capture structured logs during tests and attach them to test failure output. Failures that originate in a subprocess are opaque without this — a stack trace in the child process appears as a generic IPC error in the parent.

**CI:** Mark subprocess tests with `@pytest.mark.subprocess` and run them as a separate, serial CI step. They cannot safely parallelize with `pytest-xdist`.
