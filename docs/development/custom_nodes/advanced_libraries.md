# Advanced Libraries

Most libraries are fully described by their `griptape_nodes_library.json` manifest: the
engine reads it, imports the node modules it names, and registers those classes. An
**advanced library** is an optional Python class that lets your library run code at
points in its own lifecycle: before its nodes load, after they load, and before it is
unregistered. It also hands the engine things to register on your library's behalf:
request handlers, post-dispatch hooks, and event listeners.

This page is the author's reference for that class. For the manifest itself (metadata,
categories, declarations, dependency management) see
[Authoring Libraries](authoring_libraries.md).

## Should I write one?

**You don't need one if** your library is a fixed set of node classes in files you can
list in the manifest. That is the common case and it needs no Python beyond the nodes.

**Write one if** you need to:

- **Acquire or release process-wide resources** at library load and unload: a GPU
    context, a Python binding to a native SDK, a background thread, a connection pool.
- **Register node types the manifest doesn't list**, because the set is data-driven or
    generated. See
    [Registering node types without listing them](#registering-node-types-without-listing-them-in-the-manifest).
- **Serve a request type** your library owns, so other libraries and nodes can call into
    it. See [`get_request_handlers`](#get_request_handlers).
- **React after the engine handles a request** it already owns, such as running your own
    step every time a workflow is saved. See
    [`get_post_dispatch_hooks`](#get_post_dispatch_hooks).
- **Watch every node a workflow runs**, including the nodes inside groups, loops, and
    nodes that execute in a worker: log when each one starts and how it ends, time it, or
    send it to your own monitoring. See [Watching node runs](#watching-node-runs).
- **React to what happens in the engine process**, such as a setting changing. See
    [`get_app_event_listeners`](#get_app_event_listeners).
- **Register a competing provider** for an engine request type, such as a workflow
    publisher. See [Publishing](../../guides/publishing.md).

## Wiring one up

Point the manifest at a Python file with `advanced_library_path`, relative to the
manifest:

```json
{
  "name": "My Library",
  "advanced_library_path": "advanced_library.py",
  "nodes": []
}
```

Then subclass `AdvancedNodeLibrary` in that file and override only the hooks you need.
Every hook has a default no-op implementation:

```python
from griptape_nodes.node_library.advanced_node_library import AdvancedNodeLibrary


class MyLibrary(AdvancedNodeLibrary):
    def after_library_nodes_loaded(self, library_data, library) -> None:
        print(f"Loaded {len(library.get_registered_nodes())} nodes")
```

Three rules govern how the engine finds and builds your class. All three fail the whole
library if broken, so they are worth knowing:

- **The class must be defined in that file.** The engine scans the module for an
    `AdvancedNodeLibrary` subclass whose `__module__` matches the module it just
    imported. A subclass *imported* into the file is skipped. If you want the
    implementation to live in a package, subclass it in the file the manifest names.
- **The first match wins.** The engine takes the first qualifying subclass it finds in
    module order and stops. Define exactly one to avoid ambiguity.
- **`__init__` must take no required arguments.** The engine instantiates your class with
    no arguments. Derive whatever state you need in `__init__` or in the hooks.

If the module fails to import, contains no qualifying subclass, or cannot be
instantiated, the library is marked `UNUSABLE`, registration fails, and the editor shows
an `AdvancedLibraryLoadFailureProblem` carrying the underlying error.

## The load sequence

Understanding where each hook sits is the difference between a hook that works and one
that silently does nothing. Registering a library runs, in order:

| Step | What the engine does                                                |
| ---- | ------------------------------------------------------------------- |
| 1    | Parses and validates `griptape_nodes_library.json`                  |
| 2    | Adds the library directory and its venv site-packages to `sys.path` |
| 3    | Imports your advanced library module and instantiates your class    |
| 4    | Registers the `Library` in the `LibraryRegistry`                    |
| 5    | Persists any library settings the manifest declares                 |
| 6    | **Calls `before_library_nodes_loaded`**                             |
| 7    | Iterates `library_data.nodes`, registering each node type           |
| 8    | Registers the manifest's widgets                                    |
| 9    | **Calls `after_library_nodes_loaded`**                              |
| 10   | **Calls `get_request_handlers`** and registers what it returns      |
| 11   | **Calls `get_post_dispatch_hooks`** and registers what it returns   |
| 12   | **Calls `get_execution_event_listeners`** and registers them        |
| 13   | **Calls `get_app_event_listeners`** and registers them              |
| 14   | Computes library fitness and marks the library `LOADED`             |

Two consequences worth internalizing:

- Your class exists (step 3) before the library is registered (step 4), so
    `__init__` cannot look itself up in the `LibraryRegistry`.
- Step 7 reads `library_data.nodes` *after* step 6 has run, which is what makes dynamic
    registration possible.

Unregistering runs in the reverse spirit:

| Step | What the engine does                                                            |
| ---- | ------------------------------------------------------------------------------- |
| 1    | **Calls `before_library_unregistered`**                                         |
| 2    | Removes the library's app and execution event listeners, and its dispatch hooks |
| 3    | Removes the request handlers it registered                                      |
| 4    | Unregisters the library's widgets                                               |
| 5    | Removes the library from the `LibraryRegistry`                                  |

## The hooks

### `before_library_nodes_loaded`

```python
def before_library_nodes_loaded(self, library_data: LibrarySchema, library: Library) -> None: ...
```

Runs after your library is registered but before any node type is. Use it to set up
prerequisites that node imports depend on, or to add node definitions to
`library_data.nodes`.

`library_data` is the live `LibrarySchema` the `Library` holds, not a copy. Mutating it
here changes what the engine loads in step 7 and what it reports afterwards.

If this raises, the engine records a `BeforeLibraryCallbackProblem` and **continues
loading**. The library ends up `FLAWED` rather than failed, so a broken hook produces a
library whose nodes work but whose setup did not run. Do not rely on it having succeeded.

### `after_library_nodes_loaded`

```python
def after_library_nodes_loaded(self, library_data: LibrarySchema, library: Library) -> None: ...
```

Runs once every node type in the manifest is registered. At this point
`library.get_registered_nodes()` returns the full list, so this is the place for work
that needs to see the finished library.

This is also where you register competing-provider event handlers via
`LibraryManager.on_register_event_handler()`, which is how a library advertises itself as
a workflow publisher.

Errors are handled the same way as the before hook: an `AfterLibraryCallbackProblem` is
recorded and loading continues.

### `before_library_unregistered`

```python
def before_library_unregistered(self, library_data: LibrarySchema, library: Library) -> None: ...
```

Runs before the engine tears anything down, so your listeners and handlers are still
registered while it executes. Use it to release what you acquired at load: native
bindings, GPU contexts, background threads, connection pools.

Errors here are **logged and swallowed**. Unregistration continues regardless, so a
failing teardown cannot wedge the engine. The flip side is that a resource you fail to
release is leaked silently.

### `get_request_handlers`

```python
def get_request_handlers(self) -> list[tuple[type[RequestPayload], Callable]]: ...
```

Returns `(request_type, handler)` pairs the engine registers on your behalf, and
deregisters automatically when your library unloads. Both sync and async handlers work.
This is how a library exposes a service its own nodes, other libraries, and external
clients can all call.

There are three pieces to build. See
[the worked example](#example-a-library-that-serves-a-request-type) for all of them in
context.

**1. Define the payloads.** A request type and at least one result type, each a dataclass
registered with `PayloadRegistry` so it can be resolved by name over the WebSocket and
MCP surfaces:

```python
@dataclass
@PayloadRegistry.register
class ConvertColorspaceRequest(RequestPayload):
    color: tuple[float, float, float]
    source: str
    target: str


@dataclass
@PayloadRegistry.register
class ConvertColorspaceResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    color: tuple[float, float, float]


@dataclass
@PayloadRegistry.register
class ConvertColorspaceResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    pass
```

Put them in their own module that both your advanced library and your nodes import. The
library directory is on `sys.path` by the time either loads, so a plain
`import colorspace_events` resolves, and both files get the same module object and
therefore the same payload classes. Give that module a distinctive name: every library
directory lands on the same `sys.path`, so `events.py` risks resolving to another
library's file.

A field that carries a parameter value, such as an artifact, must be annotated `Value` from
`griptape_nodes.serialization.values` (`image: Value`) so it reads back as the same type in
another engine process. Clients, such as the editor, get it as plain JSON. A field holding a value
JSON can't represent fails to send.

**2. Return the pair from the hook.**

```python
def get_request_handlers(self) -> list[tuple[type[RequestPayload], Callable]]:
    return [(ConvertColorspaceRequest, self._handle_convert_colorspace)]
```

Annotate the return with a bare `Callable`. The base class declares
`Callable[[RequestPayload], ResultPayload]`, and a handler annotated with your concrete
request type is not assignable to that, because parameter types are contravariant.
Keeping the handler's own annotation precise is worth more than matching the base
signature exactly.

**3. Dispatch it.** Any caller in the orchestrator process sends the request through the
normal bus and gets your result back:

```python
result = GriptapeNodes.handle_request(ConvertColorspaceRequest(color=(1.0, 0.0, 0.0), source="rgb", target="hsv"))
if result.failed():
    msg = f"Attempted to convert a color in '{self.name}'. Failed because {result.result_details}"
    raise RuntimeError(msg)

success = cast("ConvertColorspaceResultSuccess", result)
```

Two rules for callers:

- **Dispatch from `process`, never from `__init__`.** A node constructor that sends a
    request can deadlock against handlers that await engine startup.
- **Always handle failure.** The providing library might not be installed, might have
    failed to load, or might have been unloaded. In those cases the request has no handler
    at all, and the engine returns a generic failure result rather than your library's
    failure type. Check `result.failed()` before narrowing to your success type.

Constraints on the mechanism:

- **Your library must own the request type.** Define the `RequestPayload` subclass in
    your own package.
- **One handler per request type, engine-wide.** Registering a type that already has a
    handler raises, surfaced as a `RequestHandlerRegistrationProblem`. For request types
    where several libraries compete and the caller picks one by name, use
    `LibraryManager.on_register_event_handler()` in `after_library_nodes_loaded` instead.
- **Registered per process.** Every library loads on the orchestrator, so its handlers
    always serve requests dispatched there. A library whose nodes execute in a worker
    also loads in that worker and registers its own copy; neither process forwards
    handler requests to the other. See
    [Node Isolation with Workers](node_isolation_with_workers.md).

Other code can discover what a loaded library exposes with
`library.get_registered_request_handler_types()`, then inspect each type with
`dataclasses.fields()` and `typing.get_type_hints()`.

### `get_post_dispatch_hooks`

```python
def get_post_dispatch_hooks(self) -> list[tuple[type[RequestPayload], Callable]]: ...
```

Returns `(request_type, callback)` pairs the engine registers on your behalf, and
deregisters when your library unloads. After the engine's own handler for that request
type produces a result, your callback is invoked with `(request, result)`. This is how a
library runs its own step when something happens in the engine — appending to an audit
log, posting to a chat channel, kicking off an export — for a request type it does not
own.

It is the mirror image of [`get_request_handlers`](#get_request_handlers), and the
difference is ownership:

|                         | `get_request_handlers`         | `get_post_dispatch_hooks`                           |
| ----------------------- | ------------------------------ | --------------------------------------------------- |
| Claims the request type | Yes — one handler engine-wide  | No — any number of libraries may hook the same type |
| When it runs            | *Instead of* an engine handler | *After* the engine's handler produced a result      |
| Can change the outcome  | It **is** the outcome          | No, notification only                               |

That is why you can hook `SaveWorkflowRequest`, which `WorkflowManager` already owns and
which `get_request_handlers` would fail to claim.

Both sync and async callbacks work. Return the pairs from the hook:

```python
def get_post_dispatch_hooks(self):
    return [(SaveWorkflowRequest, self._on_workflow_saved)]


async def _on_workflow_saved(self, request: RequestPayload, result: ResultPayload) -> None:
    if not isinstance(result, SaveWorkflowResultSuccess):
        return
    await self._append_audit_line(result.file_path)
```

Constraints on the mechanism:

- **Notification only.** The return value is ignored, and the callback cannot alter the
    result or fail the operation. One that raises is logged and otherwise ignored, and it
    does not stop other hooks on the same request.
- **Both outcomes.** The callback fires for successes and failures alike, including a
    failure synthesized from an exception that escaped the handler. Branch on the result
    type to filter, as the example above does.
- **Usually detached, sometimes not.** Whenever the engine has a live event loop the hook
    is scheduled as a detached task, so the result reaches the editor without waiting for
    it. Some paths have no such loop — CLI commands, bootstrap workflow runs, worker
    threads — and there the hook runs inline and **blocks the caller until it returns**.
    Keep hooks quick, or move slow work off-process, if they may fire on those paths.
- **Exact type matching.** A hook registered for a request type fires for that exact type
    only, never for its subclasses.
- **Read-only arguments.** Do not mutate the request or the result; both are still
    referenced by the result event the engine is about to serialize. Fields marked
    `omit_from_result` have already been cleared on the request you receive, so a hook is
    not a way to read them.
- **Do not issue engine requests from a hook.** The engine's operation-depth and
    node-execution state is process-wide, so a request sent from a hook can perturb an
    operation that is still in flight. Do external work — HTTP, file writes — instead.
- **Registered per process.** Hooks are registered on the event manager of whichever
    process loads the library. A library whose nodes execute in a worker loads in both
    processes, so each copy observes only the requests its own process handles. See
    [Node Isolation with Workers](node_isolation_with_workers.md).
- **Not durable.** Hooks still in flight when the process exits are abandoned. Do not use
    them where delivery has to be guaranteed.

A malformed pair — a callback that is not callable, or a key that is not a request type —
is reported as a `PostDispatchHookRegistrationProblem` and stops the rest of the list from
registering, leaving the library `FLAWED`. Pairs registered before the bad one stay
active, and are still removed when the library unloads.

### `get_execution_event_listeners`

```python
def get_execution_event_listeners(self) -> list[tuple[type[ExecutionPayload], Callable]]: ...
```

Returns `(event_type, callback)` pairs the engine registers on your behalf, and
deregisters when your library unloads. Execution events are what the engine reports while
a workflow runs, and the callback is called with the event's payload every time one of
that type is sent. `NodeStartProcessEvent` and `NodeFinishProcessEvent` are the pair to
listen to for watching every node run; see [Watching node runs](#watching-node-runs).

|               | `get_post_dispatch_hooks`                  | `get_execution_event_listeners`      | `get_app_event_listeners`          |
| ------------- | ------------------------------------------ | ------------------------------------ | ---------------------------------- |
| Reacts to     | A request the engine handled               | Something that happened during a run | Something that happened to the app |
| Called with   | `(request, result)`                        | The event's payload                  | The event's payload                |
| Sync or async | Both                                       | Sync only                            | Both                               |
| When it runs  | Usually detached, after the result is sent | Inline, as the event is sent         | When the event is broadcast        |

Constraints on the mechanism:

- **Synchronous only, and inline.** The callback runs on the thread that sent the event,
    before the engine moves on. For node events that is the thread running the flow,
    usually the engine's event loop, so a slow listener holds up every running node. Hand
    slow work, such as network calls or file writes, to a thread of your own. An `async`
    callback is reported as an `ExecutionEventListenerRegistrationProblem`.
- **Notification only.** The return value is ignored. A callback that raises is logged
    and otherwise ignored, and the run continues.
- **Exact type matching.** A listener registered for an event type fires for that exact
    type only, never for its subclasses.
- **Read-only arguments.** Do not mutate the payload; the engine also sends it to the
    editor.
- **Registered per process.** Listeners are registered in whichever process loads the
    library and hear only the events that process sends. See
    [Where node events are sent](#where-node-events-are-sent).
- **Needs a running engine.** Events are only delivered once the engine's event queue is
    set up, as it is in the editor, in `gtn`, and in a saved workflow run as a script. A
    script that drives the engine directly, without a workflow executor, delivers nothing.

A malformed pair — a callback that is not callable, or a key that is not an execution event
type — is reported as an `ExecutionEventListenerRegistrationProblem` and stops the rest of
the list from registering, leaving the library `FLAWED`. Pairs registered before the bad
one stay active, and are still removed when the library unloads.

### `get_app_event_listeners`

```python
def get_app_event_listeners(self) -> list[tuple[type[AppPayload], Callable]]: ...
```

Returns `(event_type, callback)` pairs for app events: events about the engine process
itself, such as `ConfigChanged` when a setting changes or `CurrentProjectChanged` when the
artist switches projects. The engine registers them on your behalf and deregisters them
when your library unloads.

```python
def get_app_event_listeners(self):
    return [(ConfigChanged, self._on_config_changed)]


def _on_config_changed(self, event: ConfigChanged) -> None:
    if event.key == "my_library.endpoint":
        self._reconnect(event.new_value)
```

Both sync and async callbacks work. A callback that raises is logged and otherwise
ignored, and the other listeners still run. Matching is on the exact type, and listeners
hear only their own process's app events. Libraries load while the engine is handling
`AppInitializationComplete`, so a listener for that event does not hear the startup that
loaded its library; do that work in `after_library_nodes_loaded` instead. A malformed pair
is reported as an `AppEventListenerRegistrationProblem`, with the same consequences as
above.

## Watching node runs

The engine sends `NodeStartProcessEvent` before every node it runs does any work, and
`NodeFinishProcessEvent` once that node's run is over, whether it succeeded, failed, or
was cancelled. Listen to both from `get_execution_event_listeners` to watch every node in
every workflow, without wrapping or replacing any node:

```python
import logging
import time
from concurrent.futures import ThreadPoolExecutor

from griptape_nodes.node_library.advanced_node_library import AdvancedNodeLibrary
from griptape_nodes.retained_mode.events.execution_events import (
    NodeFinishProcessEvent,
    NodeStartProcessEvent,
)

logger = logging.getLogger(__name__)


class NodeTimingLibrary(AdvancedNodeLibrary):
    def __init__(self) -> None:
        self._started_at: dict[str, float] = {}
        # One background thread does the slow part, so the listeners stay quick.
        self._writer = ThreadPoolExecutor(max_workers=1)

    def get_execution_event_listeners(self):
        return [
            (NodeStartProcessEvent, self._on_start),
            (NodeFinishProcessEvent, self._on_finish),
        ]

    def before_library_unregistered(self, library_data, library) -> None:
        self._writer.shutdown(wait=True)

    def _on_start(self, event: NodeStartProcessEvent) -> None:
        self._started_at[event.execution_id] = time.perf_counter()

    def _on_finish(self, event: NodeFinishProcessEvent) -> None:
        started_at = self._started_at.pop(event.execution_id, None)
        if started_at is None:
            return
        seconds = time.perf_counter() - started_at
        self._writer.submit(
            logger.info, "%s (%s) %s in %.2fs", event.node_name, event.node_type, event.outcome, seconds
        )
```

### What the events carry

| Field                   | On     | Meaning                                                                                              |
| ----------------------- | ------ | ---------------------------------------------------------------------------------------------------- |
| `node_name`             | Both   | The node on the canvas. A loop's body nodes are named as on the canvas on every iteration.           |
| `node_type`             | Both   | The node's class name.                                                                               |
| `specific_library_name` | Both   | The library the node type came from.                                                                 |
| `flow_name`             | Both   | The flow the node is in.                                                                             |
| `execution_id`          | Both   | Identifies one run of one node. The start and finish of a run share it. Compare it; don't parse it.  |
| `parent_execution_id`   | Both   | The `execution_id` of the nearest run this one is part of, or `None` at the top of a run. See below. |
| `outcome`               | Finish | `succeeded`, `failed`, or `cancelled`.                                                               |
| `error_message`         | Finish | When the run failed, the failure as one line of text, as on `NodeErrorEvent`.                        |
| `error`                 | Finish | When the run failed, the same failure in parts, as on `NodeErrorEvent`.                              |

The outcome is `cancelled` when the run was cancelled, or when the node returned early
because the artist asked to stop it. A node that raised is `failed`, even if a cancel had
been requested.

Use `execution_id` rather than `node_name` to match a finish with its start. A loop set to
**Run Group Items All at Once** runs its body nodes at the same time, so several runs of
the same node can be in progress together.

`parent_execution_id` links runs into a tree. The nodes in a group or loop's body name the
group or loop node's run as their parent, and the group or loop names whatever it is part
of in turn. It means "the nearest run this one is part of", so it stays correct if the
engine starts reporting more levels, such as each iteration of a loop.

### Which nodes are covered

Every node the engine runs sends both events: regular nodes, nodes from a library that
runs them in a worker, group nodes of every kind, loop nodes, and the nodes inside groups
and loops, however deeply nested. A loop's body nodes send a pair for every iteration.

Some nodes never start, and so send neither event:

- **Locked nodes.** They keep their values without running.
- **Start Loop nodes.** The loop runs as its End Loop node, which sends the events for
    the whole loop.
- **Nodes that fail before they start**, because an input could not be collected or the
    node failed validation. They send a `NodeErrorEvent` instead.

### Where node events are sent

Listeners hear the events of the process they are registered in, so it matters which
process runs the flow:

- **The editor's engine** sends the events for every node in the flows it runs. That
    includes nodes from a library whose nodes execute in a worker: the engine reports them
    while it waits for the worker, so you need no listener in the worker.
- **A group set to Isolated Execution, or to run in a library's environment**, runs its
    nodes in a separate engine process, except in the beta case below. That process loads
    your library too, so your listeners hear those nodes there, along with the Start and
    End nodes the engine adds to pass values in and out. The editor's engine hears only the
    group node itself, and the two runs aren't linked by `parent_execution_id`.
- **A group or loop set to Isolated Execution, with the "Isolated Execution in a worker"
    beta feature on**, runs its nodes in a worker, and the editor's engine reports them as
    it does any node that runs in a worker. Your listeners in the editor's engine hear
    every node, linked to the group's run by `parent_execution_id`, and the Start and End
    nodes a loop adds send nothing.
- **Workers** never send these events.

The link to a parent run is also lost when a node in a worker starts a subflow, and when
a node's synchronous `process()` starts one with `GriptapeNodes.handle_request`. The
nodes of those subflows report `parent_execution_id` as `None`.

### Limitations

- **The events add traffic to the editor.** They are sent to the editor as well, two for
    every node run, including every iteration of a loop.
- **Exporting to observability tools.** Turning these events into traces for tools such as
    MLflow or Datadog is tracked in
    [#5902](https://github.com/griptape-ai/griptape-nodes-engine/issues/5902).

## Registering node types without listing them in the manifest

If your node set is data-driven, generated, or simply large enough that hand-maintaining
the manifest is a chore, you can leave `"nodes": []` in the manifest and synthesize the
definitions in `before_library_nodes_loaded`.

This works because of step 6 and step 7 in [the load sequence](#the-load-sequence): the
hook runs first, `library_data` is the same object the engine reads next, and
`library_data.nodes` is an ordinary list.

```python
class MyLibrary(AdvancedNodeLibrary):
    def before_library_nodes_loaded(self, library_data, library) -> None:
        library_data.nodes.extend(
            NodeDefinition(
                class_name=spec["class_name"],
                file_path="generated_nodes.py",
                metadata=NodeMetadata(
                    category="dynamic",
                    description=spec["description"],
                    display_name=spec["display_name"],
                ),
            )
            for spec in load_specs()
        )
```

Nothing the editor reads comes from the manifest's `nodes` list. `ListNodeTypesInLibrary`
and `GetAllInfoForLibrary` both read the in-memory `Library`, so synthesized node types
appear in the node palette exactly like declared ones. Categories are still read from the
manifest, so declare every category you intend to synthesize into. Nothing validates a
node's category against the declared keys, so a mismatch fails quietly: the node type
registers fine, but the editor has no category to file it under.

Definitions added this way are indistinguishable from hand-written ones, which means they
inherit the loader's behavior: lazy module loading, one memoized import per file even
when many classes share it, stable-namespace aliasing so saved workflows, copied nodes, and
images can rebuild values your classes define, per-node problem reporting, and correct fitness.

### Where the classes come from

The engine resolves a node type by importing the file in `NodeDefinition.file_path` and
calling `getattr(module, class_name)`. A module-level `__getattr__`
([PEP 562](https://peps.python.org/pep-0562/)) satisfies that, so one file can back every
node type in the library without a single `class` statement:

```python
def __getattr__(name: str) -> type[DataNode]:
    spec = find_spec(name)
    if spec is None:
        msg = f"module {__name__!r} has no attribute {name!r}"
        raise AttributeError(msg)
    node_class = build_node_class(spec)
    globals()[name] = node_class  # cache: next lookup skips __getattr__
    return node_class
```

Cache the built class in module globals. Two lookups of the same node type must return
the same object, because the engine caches the resolved class and `isinstance` checks
compare against it.

!!! warning "Set `__module__` explicitly when you build a class"

    `type(name, bases, namespace)` does not give you the current module for free. With
    no `__module__` key in the namespace, class creation reads `__name__` from the
    calling frame's globals. Because `BaseNode` subclasses carry `ABCMeta`, that frame
    is inside the standard library's `abc` module, and your class ends up claiming
    `__module__ == "abc"`.

    Nothing complains at load time. The failure appears later: reopening a saved
    workflow looks up `__qualname__` in `__module__`, so a value your class defines
    comes back as plain data instead of as your class. Pass both explicitly:

    ```python
    return type(
        spec["class_name"],
        (DataNode,),
        {
            "__init__": __init__,
            "process": process,
            "__module__": __name__,
            "__qualname__": spec["class_name"],
        },
    )
    ```

### Why not register classes directly?

`Library.register_new_node_type()` and `Library.register_lazy_node_type()` are public,
and calling them from `after_library_nodes_loaded` also registers working node types.
Prefer synthesizing definitions anyway, for two reasons:

- **Fitness.** The engine decides whether a library loaded successfully from the
    manifest-driven loop in step 7. A library with `"nodes": []` that registers
    everything in the after hook is scored `UNUSABLE` and its registration is reported as
    a failure, even though the node types registered fine.
- **Stable namespaces.** The loader also registers a pending stable-module loader so
    `griptape_nodes.node_libraries.<library>.<file>` resolves when a saved workflow
    reopens. Registering a class directly skips that, and you own the problem.

### Limitations

- **Declaration validation only sees the manifest.** Validation of `model_usage` and
    `model_provider_usage` references runs against the manifest read from disk, so those
    declarations on synthesized nodes are never checked. A bad model reference fails at
    runtime instead of at load.
- **Node name collisions still apply.** Synthesized class names go through the same
    cross-library collision check as declared ones, and generated names collide just as
    easily. Prefix them.

## Examples

Two complete, working libraries. Copy either folder into your workspace's `libraries`
directory, register it through the editor's library settings, and restart the engine.

### Example: a library that serves a request type

A library that owns `ConvertColorspaceRequest`, serves it from its advanced library, and
consumes it from its own node:

- [`griptape_nodes_library.json`](example_request_handler_library/griptape_nodes_library.json):
    manifest declaring one node and the advanced library
- [`colorspace_events.py`](example_request_handler_library/colorspace_events.py): the
    request and result payloads, registered with `PayloadRegistry`
- [`advanced_library.py`](example_request_handler_library/advanced_library.py): returns the
    handler from `get_request_handlers` and implements it
- [`nodes.py`](example_request_handler_library/nodes.py): a node that dispatches the
    request from `process()` and handles failure

Add a **Convert Colorspace** node, set `color` to `[0, 0.5, 1]` with `source` `rgb` and
`target` `hsv`, and run it. Any other library in the same engine can now send
`ConvertColorspaceRequest` and get the same answer.

### Example: a library that registers node types dynamically

A library that registers four node types from a JSON file while declaring none in its
manifest:

- [`griptape_nodes_library.json`](example_dynamic_library/griptape_nodes_library.json):
    manifest with `"nodes": []` and one declared category
- [`node_specs.json`](example_dynamic_library/node_specs.json): the data the node set is
    derived from
- [`advanced_library.py`](example_dynamic_library/advanced_library.py): synthesizes one
    `NodeDefinition` per spec in `before_library_nodes_loaded`
- [`generated_nodes.py`](example_dynamic_library/generated_nodes.py): module
    `__getattr__` that builds each `DataNode` subclass on demand

You should see a **Dynamic** category with four nodes. Add an entry to `node_specs.json`
reusing an existing `operator` value, restart, and a fifth node appears with no change to
the manifest or the Python.
