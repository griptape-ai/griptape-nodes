# Permissions

The permission system lets you write declarative rules that gate privileged
engine operations: file IO, library registration, arbitrary Python execution,
secret access, and any other request that flows through the engine dispatcher.
Rules live in your normal config file (`griptape_nodes_config.json`) under a
top-level `permissions` key.

This page covers what rules look like, how they're evaluated, the full operator
reference, and a catalogue of worked examples you can copy-paste.

## Mental model

Every privileged engine operation is a `RequestPayload` (e.g. `WriteFileRequest`,
`RegisterLibraryFromFileRequest`, `RunArbitraryPythonStringRequest`) that flows
through one dispatcher. The permission manager registers a hook on that
dispatcher. Before any request reaches its handler, the hook evaluates the
active policy and either lets the request through, denies it (returning the
request's typed failure with `PERMISSION_DENIED`), or, eventually, prompts the
user for consent.

Rules are written in a four-axis model borrowed from policy languages like
Cedar: **principal** (who is asking), **action** (what they want to do),
**resource** (what is being acted on), **context** (ambient facts about the
world). Any axis you don't write is a wildcard. Every axis you write must
match.

## Rule shape

A rule is a JSON object with this structure:

```json
{
  "id": "user.allow-workspace-writes",
  "decision": "allow",
  "reason": "writes are scoped to the workspace by default",
  "granted_by": "user",
  "when": {
    "principal": { ... },
    "action": { ... },
    "resource": { "fields": { "<dot.path>": <match-expr> } },
    "context": { "facts": { "<dot.path>": <match-expr> } }
  }
}
```

| Field        | Required | Notes                                                                                   |
| ------------ | -------- | --------------------------------------------------------------------------------------- |
| `id`         | yes      | Stable identifier; used by `RevokePermissionRuleRequest` and shown in audit entries     |
| `decision`   | yes      | One of `"allow"`, `"deny"`, `"prompt"`                                                  |
| `reason`     | no       | Surfaced in failure messages and audit entries                                          |
| `granted_by` | no       | Free-text origin label (e.g. `"user"`, `"engine-default"`, `"license:enterprise@2026"`) |
| `when`       | no       | Combined matcher; an empty `when` matches everything                                    |

## Policy and merging

The `permissions` block in your config holds a `policy`:

```json
{
  "permissions": {
    "enabled": true,
    "consent_prompts_enabled": true,
    "audit_log_max_entries": 1000,
    "policy": {
      "default_decision": "allow",
      "rules": [ ... ]
    }
  }
}
```

Rules are evaluated **first-match-wins** in list order. If no rule matches, the
policy's `default_decision` applies.

The default `default_decision` is `"allow"`, so an unconfigured engine behaves
exactly as before. To lock down by default, set `"default_decision": "deny"`
and add explicit allow rules.

Like every other engine setting, the `permissions` block layers across config
files: built-in defaults → user → project-adjacent → workspace → environment
variables. The `PermissionManager` reads each layer's `permissions` block
separately and assembles the active policy at evaluation time:

- Each layer's `policy.rules` are concatenated **highest-priority layer
    first** (env → workspace → project → user → defaults), so a workspace rule
    fires ahead of a user rule under first-match-wins.
- License-imposed rules sit ahead of every config layer in evaluation order.
- Scalar settings (`enabled`, `consent_prompts_enabled`, `audit_log_max_entries`,
    `policy.default_decision`) follow the usual layered-config precedence: the
    highest-priority layer that explicitly sets a value wins; lower layers do
    not override it. A layer that does not write `default_decision` is treated
    as silent rather than as setting it to the schema default of `"allow"`.
- Each rule's `granted_by` is auto-stamped with the layer name (`"user"`,
    `"workspace"`, `"project"`, `"env"`, `"defaults"`) when the rule did not
    explicitly carry one, so audit entries identify the source config file.
- `GrantPermissionRuleRequest` and `RevokePermissionRuleRequest` operate on
    the user layer only. Rules from other layers are read-only at runtime;
    edit them by hand in the layer's `griptape_nodes_config.json`.

## Operators

Every matcher value is a small object with an `op` discriminator:

| Operator     | Shape                                          | Meaning                                              |
| ------------ | ---------------------------------------------- | ---------------------------------------------------- |
| `equals`     | `{"op": "equals", "value": <any>}`             | Strict equality                                      |
| `in`         | `{"op": "in", "values": [<any>...]}`           | Membership; against a list-valued field, any-overlap |
| `glob`       | `{"op": "glob", "pattern": "..."}`             | `fnmatch`-style glob against a string                |
| `path_under` | `{"op": "path_under", "root": "<path>"}`       | Macro-expanded canonical path containment            |
| `not`        | `{"op": "not", "expr": <match-expr>}`          | Negation                                             |
| `all_of`     | `{"op": "all_of", "exprs": [<match-expr>...]}` | Conjunction                                          |
| `any_of`     | `{"op": "any_of", "exprs": [<match-expr>...]}` | Disjunction                                          |

The `path_under` operator expands `${workspace}` and `${static_files_directory}`
macros before comparing, so policies stay portable across machines.

## Axes

### Principal — who is asking

```json
"principal": {
  "kind": ["node"],
  "library": { "op": "equals", "value": "advanced-image-library" },
  "node_type": { "op": "glob", "pattern": "*UpscaleNode*" },
  "topic": { "op": "equals", "value": "ws://editor" }
}
```

`kind` is an array (any-of) of `"engine"`, `"node"`, `"client"`. The other
fields are predicates and only meaningful for the matching kind:

- `library` and `node_type` apply when `kind` includes `"node"`.
- `topic` applies when `kind` includes `"client"` (the websocket response
    topic identifies which connected editor / MCP client issued the request).

### Action — what they want to do

```json
"action": {
  "request_type": { "op": "in", "values": ["WriteFileRequest", "DeleteFileRequest"] }
}
```

`request_type` is the class name of the `RequestPayload` (e.g.
`WriteFileRequest`, `RegisterLibraryFromFileRequest`,
`RunArbitraryPythonStringRequest`, `CreateNodeRequest`).

### Resource — what is being acted on

```json
"resource": {
  "fields": {
    "file_path": { "op": "path_under", "root": "${workspace}" }
  }
}
```

Keys under `fields` are dot-paths into the request payload's dataclass. For
example, `WriteFileRequest` has a `file_path` field, so `"file_path": ...`
matches against it. Multiple keys are AND'd.

### Context — ambient facts

```json
"context": {
  "facts": {
    "loaded_libraries.names": { "op": "in", "values": ["advanced-image-library"] }
  }
}
```

Keys under `facts` are dot-paths into the merged fact tree. See
[Context fact reference](#context-fact-reference) for the complete list of
built-in facts and per-request enrichers.

## Context fact reference

Facts are values made available to the `context` axis of a rule. Two flavours:

- **Built-in providers** registered by `PermissionManager` and refreshed via
    formally defined engine events. Available everywhere; cached between
    evaluations and invalidated when the underlying state changes.
- **Per-request enrichers** registered by individual managers. Only present
    while the matching request type is being evaluated; published under the
    `request.*` namespace.

### Built-in facts

| Path                     | Type          | Refreshes when              | Notes                                                                     |
| ------------------------ | ------------- | --------------------------- | ------------------------------------------------------------------------- |
| `workspace.path`         | `str \| None` | `ConfigChanged`             | Resolved absolute path of the active workspace                            |
| `engine.id`              | `str \| None` | never                       | Stable engine session identifier                                          |
| `loaded_libraries.names` | `list[str]`   | `LibraryLoadedNotification` | Names of every library currently registered with `LibraryRegistry`        |
| `current_node.library`   | `str \| None` | node execution boundary     | Library name of the node currently executing, or `None` outside execution |
| `current_node.node_type` | `str \| None` | node execution boundary     | Class name of the node currently executing                                |
| `current_node.node_name` | `str \| None` | node execution boundary     | Instance name of the node currently executing                             |

`current_node.*` is populated whenever something has called
`PermissionManager.push_principal(...)` and not yet popped. The intended
caller is the node executor at the boundaries of `node.aprocess()`. Outside
a push/pop block, every `current_node.*` field is `None`, so rules using
them only fire during node execution.

### Per-request enricher facts

These are published under `request.*` for the duration of one rule
evaluation, derived from the request payload itself. Available facts depend
on which manager has registered an enricher for that request type.

| Request type                     | Path                                            | Type          | Notes                                                                                          |
| -------------------------------- | ----------------------------------------------- | ------------- | ---------------------------------------------------------------------------------------------- |
| `RegisterLibraryFromFileRequest` | `request.metadata.name`                         | `str \| None` | `name` field from the library JSON                                                             |
| `RegisterLibraryFromFileRequest` | `request.metadata.declarations.lifecycle_stage` | `str \| None` | Stage from a `LifecycleStageLibraryProperty` (`STABLE`, `BETA`, `ALPHA`, `LABS`, `DEPRECATED`) |
| `RegisterLibraryFromFileRequest` | `request.metadata.declarations.types`           | `list[str]`   | Flat list of declaration `type` strings, useful for `in` matchers                              |

Enrichers are best-effort: missing files, malformed JSON, or unexpected
shapes yield no facts, so rules that depended on them simply don't fire and
evaluation falls through.

### Adding your own facts

Managers and library code can publish additional facts through the same
registry:

```python
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.retained_mode.managers.permissions import FactInvalidator

pm = GriptapeNodes.PermissionManager()

# A static fact
pm.facts.register_provider(
    "site.region",
    lambda: "us-east-1",
    invalidator=FactInvalidator.NEVER,
)

# A request-scoped fact for a specific request type
pm.facts.register_request_enricher(
    "WriteFileRequest",
    lambda req: {"size_hint": len(req.content) if isinstance(req.content, (bytes, str)) else 0},
)
```

Providers must be cheap and synchronous, and must not themselves issue
requests through the dispatcher (re-entrancy would deadlock). The
`FactInvalidator` enum maps each cache invalidator to a real engine event
so you don't need a separate polling loop.

## Worked examples

### Lock writes to your workspace

```json
{
  "permissions": {
    "policy": {
      "default_decision": "allow",
      "rules": [
        {
          "id": "user.deny-writes-outside-workspace",
          "decision": "deny",
          "reason": "writes are scoped to the active workspace",
          "when": {
            "action": { "request_type": { "op": "equals", "value": "WriteFileRequest" } },
            "resource": {
              "fields": {
                "file_path": {
                  "op": "not",
                  "expr": { "op": "path_under", "root": "${workspace}" }
                }
              }
            }
          }
        }
      ]
    }
  }
}
```

Allows writes anywhere inside the workspace, denies writes anywhere else. Read
operations are unaffected because the rule only matches `WriteFileRequest`.

### Block a specific library at startup

```json
{
  "id": "user.deny-experimental-library",
  "decision": "deny",
  "reason": "experimental library disabled",
  "when": {
    "action": { "request_type": { "op": "equals", "value": "RegisterLibraryFromFileRequest" } },
    "resource": {
      "fields": {
        "file_path": { "op": "glob", "pattern": "*experimental-library*" }
      }
    }
  }
}
```

The engine logs the denial during library load and the library appears as
`PENDING` in the library status panel. Other libraries load normally.

### Block arbitrary Python from external clients

```json
{
  "id": "user.deny-arbitrary-python-from-clients",
  "decision": "deny",
  "reason": "arbitrary Python execution from external clients is disabled",
  "when": {
    "principal": { "kind": ["client"] },
    "action": { "request_type": { "op": "equals", "value": "RunArbitraryPythonStringRequest" } }
  }
}
```

`RunArbitraryPythonStringRequest` from the editor or any connected MCP client
is denied; the engine itself and your own nodes can still call it. This is a
good default for any setup where the editor talks to a remote engine.

### Allow a specific library to write to a specific subdirectory

```json
{
  "id": "user.allow-image-lib-outputs",
  "decision": "allow",
  "when": {
    "principal": {
      "kind": ["node"],
      "library": { "op": "equals", "value": "advanced-image-library" }
    },
    "action": { "request_type": { "op": "equals", "value": "WriteFileRequest" } },
    "resource": {
      "fields": {
        "file_path": { "op": "path_under", "root": "${workspace}/outputs" }
      }
    }
  }
}
```

Combines all four axes: the principal must be a node from the named library,
the action must be `WriteFileRequest`, and the target path must live under
`${workspace}/outputs`. Anything else falls through to subsequent rules or the
policy default.

### Restrict a library to read-only operations

```json
[
  {
    "id": "user.allow-readonly-for-restricted-lib",
    "decision": "allow",
    "when": {
      "principal": {
        "kind": ["node"],
        "library": { "op": "equals", "value": "untrusted-library" }
      },
      "action": {
        "request_type": {
          "op": "in",
          "values": [
            "ReadFileRequest",
            "GetFileInfoRequest",
            "ListDirectoryRequest"
          ]
        }
      }
    }
  },
  {
    "id": "user.deny-everything-else-for-restricted-lib",
    "decision": "deny",
    "reason": "untrusted-library is restricted to read-only operations",
    "when": {
      "principal": {
        "kind": ["node"],
        "library": { "op": "equals", "value": "untrusted-library" }
      }
    }
  }
]
```

Two rules in order: the first allow-lists read operations for the named
library; the second catches everything else and denies it. Other libraries are
unaffected.

### Allow only known MCP clients

```json
[
  {
    "id": "user.allow-known-mcp-clients",
    "decision": "allow",
    "when": {
      "principal": {
        "kind": ["client"],
        "topic": {
          "op": "any_of",
          "exprs": [
            { "op": "glob", "pattern": "*claude-desktop*" },
            { "op": "glob", "pattern": "*cursor*" }
          ]
        }
      }
    }
  },
  {
    "id": "user.deny-unknown-clients",
    "decision": "deny",
    "reason": "only allow-listed MCP clients are permitted",
    "when": { "principal": { "kind": ["client"] } }
  }
]
```

External clients are only allowed if their topic matches one of the listed
patterns. Engine-internal and node-issued requests aren't covered by either
rule and continue under the policy default.

### Block libraries by lifecycle stage

Libraries authored against schema 0.8.0+ can declare a lifecycle stage
(`STABLE`, `BETA`, `ALPHA`, `LABS`, `DEPRECATED`). `LibraryManager` parses
the library's JSON during a `RegisterLibraryFromFileRequest` evaluation and
publishes the declarations as facts under `request.metadata.declarations.*`,
so permission rules can match against them directly.

```json
{
  "id": "user.deny-labs-libraries",
  "decision": "deny",
  "reason": "labs-stage libraries are not permitted in this workspace",
  "when": {
    "action": { "request_type": { "op": "equals", "value": "RegisterLibraryFromFileRequest" } },
    "context": {
      "facts": {
        "request.metadata.declarations.lifecycle_stage": { "op": "equals", "value": "LABS" }
      }
    }
  }
}
```

With this rule active, any library whose `griptape_nodes_library.json`
contains a `lifecycle_stage` declaration set to `LABS` is rejected at
registration time and never reaches the loader. `STABLE`, `BETA`, and so on
pass through. To block multiple stages at once, swap `equals` for `in`:

```json
"request.metadata.declarations.lifecycle_stage": {
  "op": "in",
  "values": ["LABS", "ALPHA"]
}
```

For a coarser "any library that declares a lifecycle stage at all" rule,
match against the flattened types list:

```json
"request.metadata.declarations.types": {
  "op": "in",
  "values": ["lifecycle_stage"]
}
```

The enricher is best-effort: a library with a missing or malformed JSON file
yields no facts, so the rule simply doesn't fire and registration falls
through to subsequent rules or the policy default. It also accepts the
directory form of `file_path` (the path to the folder containing
`griptape_nodes_library.json`) and resolves a `library_name` to the JSON the
loader will read — a tracked library by its known path, or, when the request
permits discovery, the matching file found by a read-only library scan — so a
registration by name is gated by the same rules as a registration by path.

### Conditional rule via context facts

```json
{
  "id": "user.deny-writes-when-cloud-storage-loaded",
  "decision": "deny",
  "reason": "local writes are off when cloud-storage library is active",
  "when": {
    "action": { "request_type": { "op": "equals", "value": "WriteFileRequest" } },
    "context": {
      "facts": {
        "loaded_libraries.names": {
          "op": "in",
          "values": ["griptape-cloud-storage"]
        }
      }
    }
  }
}
```

Active only while `griptape-cloud-storage` is in the loaded library set. As
soon as that library is unloaded, the rule stops firing.

### Combine matchers with `all_of` / `any_of` / `not`

```json
{
  "id": "user.deny-bin-writes-into-workspace-root",
  "decision": "deny",
  "when": {
    "action": { "request_type": { "op": "equals", "value": "WriteFileRequest" } },
    "resource": {
      "fields": {
        "file_path": {
          "op": "all_of",
          "exprs": [
            { "op": "path_under", "root": "${workspace}" },
            {
              "op": "not",
              "expr": { "op": "path_under", "root": "${workspace}/bin" }
            },
            { "op": "glob", "pattern": "*.bin" }
          ]
        }
      }
    }
  }
}
```

`all_of` expresses "all of these must hold for this field." Operators nest
freely; `any_of` and `not` work the same way.

### Tighten by switching the default

```json
{
  "permissions": {
    "policy": {
      "default_decision": "deny",
      "rules": [
        {
          "id": "engine.allow-reads-anywhere",
          "decision": "allow",
          "when": {
            "action": {
              "request_type": {
                "op": "in",
                "values": ["ReadFileRequest", "GetFileInfoRequest", "ListDirectoryRequest"]
              }
            }
          }
        },
        {
          "id": "engine.allow-writes-under-workspace",
          "decision": "allow",
          "when": {
            "action": { "request_type": { "op": "equals", "value": "WriteFileRequest" } },
            "resource": {
              "fields": { "file_path": { "op": "path_under", "root": "${workspace}" } }
            }
          }
        },
        {
          "id": "engine.allow-engine-itself",
          "decision": "allow",
          "when": { "principal": { "kind": ["engine"] } }
        }
      ]
    }
  }
}
```

`default_decision: deny` flips the engine into allow-list mode: nothing is
permitted unless an explicit rule allows it. The three rules above are roughly
the minimum to keep a development engine functional.

## Programmatic API

Permissions can also be managed at runtime via the request dispatcher (the
manager's own request types are exempt from the hook so a too-restrictive
policy can always be repaired):

```python
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.retained_mode.events.permission_events import (
    GetEffectivePolicyRequest,
    GrantPermissionRuleRequest,
    ListPermissionDecisionsRequest,
    RevokePermissionRuleRequest,
)

# Add a rule (persisted into user config)
GriptapeNodes.handle_request(GrantPermissionRuleRequest(rule={
    "id": "session.deny-arbitrary-python",
    "decision": "deny",
    "when": {
        "action": {"request_type": {"op": "equals", "value": "RunArbitraryPythonStringRequest"}}
    },
}))

# Read the effective policy (license + user, in evaluation order)
policy = GriptapeNodes.handle_request(GetEffectivePolicyRequest()).policy

# Tail recent decisions
decisions = GriptapeNodes.handle_request(
    ListPermissionDecisionsRequest(limit=20)
).decisions

# Remove a user rule
GriptapeNodes.handle_request(
    RevokePermissionRuleRequest(rule_id="session.deny-arbitrary-python")
)
```

These four request types are the public surface. Editor UIs build on top of
them; license and policy automation tools should use them rather than editing
config files by hand.

### MCP exposure

All four request types are exposed as tools on the engine's MCP server
(`SUPPORTED_REQUEST_EVENTS` in `src/griptape_nodes/servers/mcp.py`):

- `GetEffectivePolicyRequest`
- `GrantPermissionRuleRequest`
- `RevokePermissionRuleRequest`
- `ListPermissionDecisionsRequest`

This means any MCP client (the editor, an external admin tool, an agent like
Claude Desktop) can read and edit the user policy through the standard MCP
toolset. Two things to know:

- **The dispatcher hook does not gate these requests.** They're listed in
    `PERMISSION_OWN_REQUEST_TYPES` and exempted from policy evaluation, so a
    too-restrictive policy can always be repaired. That means a connected MCP
    client can grant or revoke user-policy rules without going through any
    permission check.
- **License-imposed rules are not editable through MCP.** They are owned by
    `PermissionManager.set_license_policy()`, which is not exposed as a request
    type. `RevokePermissionRuleRequest` against a license rule id fails with a
    clear reason. Use the license layer for hard constraints that even an MCP
    client should not be able to disable.

If you expose the MCP server to untrusted clients (remote, unauthenticated),
gate these tools at the transport layer or place equivalent constraints in
the license layer. The local-only default (binding to `127.0.0.1`) and the
fact that the user already controls their own config file mean the standard
local setup carries no additional risk.

## Audit log and decision events

Every evaluation appends a structured entry to an in-memory ring buffer
(bounded by `audit_log_max_entries`) and broadcasts a
`PermissionDecisionEvent` on the standard `AppPayload` event bus. Entry shape:

```json
{
  "rule_id": "user.deny-experimental-library",
  "decision": "deny",
  "principal_kind": "engine",
  "principal_label": "engine",
  "action_request_type": "RegisterLibraryFromFileRequest",
  "resource_summary": {
    "library_name": null,
    "file_path": ".../experimental-library/griptape_nodes_library.json"
  },
  "inspected_paths": ["action.request_type", "resource.file_path"],
  "reason": "experimental library disabled"
}
```

`inspected_paths` records which match-paths the rule actually consulted, so
"why did this fire?" is trivially answerable from the audit alone. To watch
decisions live, subscribe to `PermissionDecisionEvent`:

```python
from griptape_nodes.retained_mode.events.permission_events import (
    PermissionDecisionEvent,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

def on_decision(event: PermissionDecisionEvent) -> None:
    if event.decision == "deny":
        print(f"DENY {event.action_request_type} ({event.rule_id}): {event.reason}")

GriptapeNodes.EventManager().add_listener_to_app_event(
    PermissionDecisionEvent, on_decision
)
```

## License layer

Some deployments need rules that the user cannot remove, even by hand-editing
their config file. The permission manager exposes a separate license layer for
this purpose:

```python
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.retained_mode.managers.permissions import (
    PermissionPolicy,
    PermissionRule,
    Decision,
    WhenClause,
)
from griptape_nodes.retained_mode.managers.permissions.matchers import ActionMatch
from griptape_nodes.retained_mode.managers.permissions.schema import EqualsExpr

GriptapeNodes.PermissionManager().set_license_policy(
    PermissionPolicy(rules=[
        PermissionRule(
            id="license.no-arbitrary-python",
            decision=Decision.DENY,
            reason="this license forbids arbitrary Python",
            when=WhenClause(
                action=ActionMatch(
                    request_type=EqualsExpr(value="RunArbitraryPythonStringRequest"),
                ),
            ),
        ),
    ]),
)
```

License rules are evaluated **before** user rules and are never persisted to
user config. A user editing `griptape_nodes_config.json` cannot remove a
license-imposed rule; `RevokePermissionRuleRequest` against a license rule id
fails with a clear reason. Calling `clear_license_policy()` drops the entire
license fragment (used by license revocation paths).

The license layer is intended for whoever loads license files (a future
`LicenseManager`) to call programmatically; there's no JSON config surface for
it on purpose.

## Failure shape

When a request is denied, the dispatcher returns the request's typed failure
payload — not a generic error. For `WriteFileRequest`:

```python
result = GriptapeNodes.handle_request(WriteFileRequest(...))
if not result.succeeded():
    # type(result) is WriteFileResultFailure
    # result.failure_reason is FileIOFailureReason.PERMISSION_DENIED
    print(result.result_details)
    # → "Attempted to dispatch WriteFileRequest. Failed because permission
    #    was denied by rule 'user.deny-writes-outside-workspace' [deny]
    #    (writes are scoped to the active workspace)."
```

This means existing handler-side type assumptions keep working: a caller that
already does `isinstance(result, WriteFileResultFailure)` doesn't need to
learn a new failure type for permission denials.

For request types that don't have a typed failure companion, a generic
`PermissionDeniedResult` is returned instead.

## Settings reference

Top-level keys under the `permissions` block:

| Key                       | Type   | Default   | Description                                                                                |
| ------------------------- | ------ | --------- | ------------------------------------------------------------------------------------------ |
| `enabled`                 | bool   | `true`    | When `false`, the dispatcher hook is skipped entirely                                      |
| `consent_prompts_enabled` | bool   | `true`    | Affects how `prompt` decisions are surfaced (currently treated as deny pending consent UI) |
| `audit_log_max_entries`   | int    | `1000`    | Bound on the in-memory audit ring buffer                                                   |
| `policy.rules`            | list   | `[]`      | Ordered rules; first match wins                                                            |
| `policy.default_decision` | string | `"allow"` | Fall-through when no rule matches; one of `allow`, `deny`, `prompt`                        |

## Limitations

- **`prompt` decisions currently deny** with a `prompt-not-implemented` tag in
    the audit entry. Consent UI lives behind a future change; until then, treat
    `prompt` as "deny but mark distinctly so I can find these later."
- **The dispatcher chokepoint isn't fully closed.** Some manager methods are
    invoked as plain Python calls inside the engine instead of routed through
    the dispatcher, which means those specific operations bypass the permission
    hook today. The audit catalogues them; the fix is mechanical and is being
    landed incrementally. In the meantime, if a rule you wrote doesn't fire,
    check whether the operation actually reaches `EventManager.handle_request`.
- **Fact provider state is lazy by default.** Custom fact providers can opt in
    to invalidation via `ConfigChanged` and `LibraryLoadedNotification`; the
    defaults handle these. If you author a provider that derives from other
    state, declare its invalidator explicitly.
