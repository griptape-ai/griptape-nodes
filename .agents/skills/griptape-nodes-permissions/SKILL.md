---
name: griptape-nodes-permissions
description: Author and manage permission rules on the engine through its MCP server. Use when the user asks to allow or deny a privileged operation, lock down a library, restrict an MCP client, gate writes to a path, audit recent denials, or revoke an existing rule. Triggers include "set up a permission rule", "block this library at startup", "deny X from doing Y", "allow this library to write to Z", "what's been denied recently", "audit log of permission denials", "lock this engine down", "revoke that rule".
---

# Griptape Nodes Permission Authoring Guide

This skill covers authoring, applying, and verifying permission rules through the engine's MCP server. The permission system enforces declarative policy at the request dispatcher; rules ride normal engine config and are first-match-wins.

## Mental Model

- **Rules** evaluate four axes: **principal** (who is asking — engine / node / client), **action** (request type), **resource** (fields of the request payload), **context** (ambient facts). Populated axes are AND'd; unpopulated axes are wildcards.
- **First-match-wins** in policy order. License rules evaluate first, then user rules. If nothing matches, the policy's `default_decision` applies.
- **License rules trump user rules** and are not editable through MCP. Use them for hard constraints. User rules are the everyday surface and are what `Grant`/`Revoke` operate on.
- **The dispatcher hook short-circuits with the request's typed failure.** A denied `WriteFileRequest` returns `WriteFileResultFailure` with `failure_reason = PERMISSION_DENIED`, not a generic error.
- **Default behaviour is `allow`.** An engine with no rules behaves exactly as it always has; ratchet down by adding deny rules or by switching `default_decision` to `deny`.

## MCP Tools

Four MCP tools manage policy. They are exempt from the policy hook so a too-restrictive policy can always be repaired:

| Tool                                            | Purpose                                                                         |
| ----------------------------------------------- | ------------------------------------------------------------------------------- |
| `griptape_nodes_GrantPermissionRuleRequest`     | Append a rule to the user policy (persisted into user config).                  |
| `griptape_nodes_RevokePermissionRuleRequest`    | Remove a user rule by `id`. License rules cannot be revoked here.               |
| `griptape_nodes_GetEffectivePolicyRequest`      | Read the merged policy (license rules first, then user rules) for verification. |
| `griptape_nodes_ListPermissionDecisionsRequest` | Tail the in-memory audit ring buffer (`limit` argument optional).               |

## Rule Shape

```json
{
  "id": "user.short-stable-identifier",
  "decision": "allow" | "deny" | "prompt",
  "reason": "human-readable explanation, surfaced in failures and audit",
  "granted_by": "user",
  "when": {
    "principal": { ... },
    "action":    { ... },
    "resource":  { "fields": { "<dot.path>": <expr> } },
    "context":   { "facts":  { "<dot.path>": <expr> } }
  }
}
```

`prompt` decisions currently behave as deny with a `prompt-not-implemented` audit tag (consent UI is future work). Default to `allow` or `deny` for now.

## Operator Cheat Sheet

| Operator     | Shape                                    | Use                                                                                               |
| ------------ | ---------------------------------------- | ------------------------------------------------------------------------------------------------- |
| `equals`     | `{"op": "equals", "value": <any>}`       | Strict equality                                                                                   |
| `in`         | `{"op": "in", "values": [<any>...]}`     | Membership; against a list-valued field, any-overlap                                              |
| `glob`       | `{"op": "glob", "pattern": "..."}`       | fnmatch-style glob against a string                                                               |
| `path_under` | `{"op": "path_under", "root": "<path>"}` | Macro-expanded canonical path containment. `${workspace}` and `${static_files_directory}` expand. |
| `not`        | `{"op": "not", "expr": <expr>}`          | Negation                                                                                          |
| `all_of`     | `{"op": "all_of", "exprs": [<expr>...]}` | Conjunction                                                                                       |
| `any_of`     | `{"op": "any_of", "exprs": [<expr>...]}` | Disjunction                                                                                       |

## Principal Axis

```json
"principal": {
  "kind": ["engine"] | ["node"] | ["client"] | <multiple>,
  "library":   <expr>,   // applies when kind includes "node"
  "node_type": <expr>,   // applies when kind includes "node"
  "topic":     <expr>    // applies when kind includes "client"
}
```

`engine` covers requests originating inside the engine itself (startup, internal flows). `node` covers requests issued from inside an executing node. `client` covers requests received over the wire from a connected MCP client / editor — `topic` is the response topic of that client.

## Common Resource Fields

Match against fields of the request payload via dot-paths under `resource.fields`. The most common ones:

| Request type                      | Field                   | Notes                                                         |
| --------------------------------- | ----------------------- | ------------------------------------------------------------- |
| `WriteFileRequest`                | `file_path`             | Almost always paired with `path_under` against `${workspace}` |
| `ReadFileRequest`                 | `file_path`             | Same                                                          |
| `RegisterLibraryFromFileRequest`  | `file_path`             | Path to library JSON or directory                             |
| `RegisterLibraryFromFileRequest`  | `library_name`          | Optional library name when registering by name                |
| `RunArbitraryPythonStringRequest` | `python_string`         | Use `glob` or `not.glob` to gate by snippet content           |
| `CreateNodeRequest`               | `node_type`             | Class name of the node being created                          |
| `CreateNodeRequest`               | `specific_library_name` | Library scope of the create                                   |

## Common Context Facts

Match ambient state under `context.facts`:

| Path                                            | Type          | Refreshes when              | Notes                                                                                                 |
| ----------------------------------------------- | ------------- | --------------------------- | ----------------------------------------------------------------------------------------------------- |
| `workspace.path`                                | `str`         | `ConfigChanged`             | Active workspace absolute path                                                                        |
| `engine.id`                                     | `str`         | never                       | Stable engine session id                                                                              |
| `loaded_libraries.names`                        | `list[str]`   | `LibraryLoadedNotification` | Names of currently registered libraries                                                               |
| `current_node.library`                          | `str \| None` | execution boundary          | Library of the node currently executing                                                               |
| `current_node.node_type`                        | `str \| None` | execution boundary          | Class name of the node currently executing                                                            |
| `current_node.node_name`                        | `str \| None` | execution boundary          | Instance name of the node currently executing                                                         |
| `request.metadata.declarations.lifecycle_stage` | `str \| None` | per-request                 | Only set on `RegisterLibraryFromFileRequest`. One of `STABLE`, `BETA`, `ALPHA`, `LABS`, `DEPRECATED`. |
| `request.metadata.declarations.types`           | `list[str]`   | per-request                 | Only set on `RegisterLibraryFromFileRequest`. Flat list of declaration `type` strings.                |
| `request.metadata.name`                         | `str \| None` | per-request                 | Library name from the JSON being registered.                                                          |

## Worked Recipes

### Lock writes to the workspace

```json
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
```

### Block a specific library at startup

```json
{
  "id": "user.deny-experimental-library",
  "decision": "deny",
  "reason": "experimental library disabled for this engine",
  "when": {
    "action": { "request_type": { "op": "equals", "value": "RegisterLibraryFromFileRequest" } },
    "resource": {
      "fields": { "file_path": { "op": "glob", "pattern": "*experimental-library*" } }
    }
  }
}
```

### Block any LABS-stage library

Uses the per-request enricher that `LibraryManager` ships, so this works against any library whose JSON declares `lifecycle_stage = LABS`.

```json
{
  "id": "user.deny-labs-libraries",
  "decision": "deny",
  "reason": "labs-stage libraries are not permitted",
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

To block multiple stages: `"op": "in", "values": ["LABS", "ALPHA"]`.

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
      "fields": { "file_path": { "op": "path_under", "root": "${workspace}/outputs" } }
    }
  }
}
```

### Restrict a library to read-only operations

Two rules in order — earlier rules win. The first allow-lists reads for the named library; the second catches everything else from that library and denies it.

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
          "values": ["ReadFileRequest", "GetFileInfoRequest", "ListDirectoryRequest"]
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
        "loaded_libraries.names": { "op": "in", "values": ["griptape-cloud-storage"] }
      }
    }
  }
}
```

## Author + Verify Recipe

After authoring a rule, always verify before declaring success. Three MCP calls:

```
1. griptape_nodes_GrantPermissionRuleRequest(rule={ ... })
   → returns rule_id on success.

2. griptape_nodes_GetEffectivePolicyRequest()
   → confirm the rule appears in the merged policy, in the position you expect.

3. (optional, after triggering the gated action)
   griptape_nodes_ListPermissionDecisionsRequest(limit=20)
   → confirm the rule actually fired. Each entry has rule_id, decision,
     principal_label, action_request_type, resource_summary, inspected_paths,
     reason. inspected_paths shows which match paths the rule consulted.
```

If `Grant` fails with `GrantPermissionRuleResultFailure`, the rule didn't validate. Read the `result_details`; the most common cause is an unknown operator in `op` (only the seven in the cheat sheet are accepted).

## Revoking

```
griptape_nodes_RevokePermissionRuleRequest(rule_id="user.deny-experimental-library")
```

Failure reasons:

- `result_details` mentions "no user rule with that id exists" → the id was wrong, or the rule is license-imposed (license rules cannot be revoked through this API).

## Batched authoring

Many rules at once go through `griptape_nodes_EventRequestBatch`. Each inner request is one `GrantPermissionRuleRequest`. Per-slot failure does not abort siblings, so walk the result array and check `ok: true` on every entry:

```json
{
  "requests": [
    {"request_type": "GrantPermissionRuleRequest",
     "request": {"rule": { "id": "user.allow-readonly", "decision": "allow", "when": { ... } }}},
    {"request_type": "GrantPermissionRuleRequest",
     "request": {"rule": { "id": "user.deny-everything-else", "decision": "deny", "when": { ... } }}}
  ]
}
```

## Critical Idioms

- **Stable, prefixed `id`s.** Use a `user.<topic>-<verb>-<scope>` shape (e.g. `user.deny-writes-outside-workspace`). Stable ids let `Revoke` and audit-log filtering work.
- **Always set `reason`.** It surfaces in the failure message the user sees and in audit entries; debugging policy without it is painful.
- **First-match-wins means order matters.** When granting allow + deny pairs (e.g. read-only restriction), grant the **allow** first so it wins for permitted ops; the deny then catches everything else.
- **Verify after every grant.** A mistyped operator silently fails validation; a mistyped field path silently doesn't fire. The dispatcher won't tell you a rule is unreachable. `GetEffectivePolicyRequest` + a probe of the gated action confirm both shape and effect.
- **Don't ratchet `default_decision` to `deny` casually.** It locks the engine into allow-list mode and you must explicitly allow every privileged op. For most demos, leave it `allow` and add `deny` rules surgically.
- **Read-only requests usually don't need rules.** `Get*` / `List*` / `Describe*` requests are not state-modifying; default-allow is normally what you want. Focus deny rules on `Write*`, `Delete*`, `Register*`, `Run*`, `Set*`, `Create*`, `Execute*`.

## Gotchas

### Manager request types are exempt from the hook

The four permission tools (`Grant`, `Revoke`, `GetEffectivePolicy`, `ListPermissionDecisions`) bypass policy evaluation by design so the user can always repair a too-restrictive policy. This means a connected MCP client can edit user rules without a policy check. License rules (set via `PermissionManager.set_license_policy()`) are NOT exposed as MCP tools and are the right place for hard constraints.

### Rules do not auto-fire on operations that bypass the dispatcher

The permission hook fires for every `RequestPayload` that flows through `EventManager.handle_request` / `ahandle_request`. Some manager methods are still invoked as plain Python calls inside the engine (audit at `permission_bypass_audit.md`); rules don't fire on those paths. If a rule you wrote isn't firing, confirm the operation actually reaches the dispatcher (check `ListPermissionDecisionsRequest` — if there's no entry for that `action_request_type`, the dispatcher never saw it).

### Persisted into user config

`Grant` writes to `~/.config/griptape_nodes/griptape_nodes_config.json` under the `permissions.policy.rules` key. To inspect or hand-edit, that's the file. License-imposed rules are NOT written there — they live in memory only.

### `path_under` does canonical containment, not string prefix

`/a/b` is not under `/a/b-other`. Symlinks are followed. The macro `${workspace}` resolves to the active workspace's absolute path before comparison, so policies stay portable across machines.

### glob patterns are fnmatch, not regex

`*` matches any sequence; `?` one char; `[abc]` a class. No anchors, no `\d`, no alternation. For more, combine `glob` patterns under `any_of`.

## End-to-End Example: "Block any library in LABS lifecycle stage"

The complete demo flow, end-to-end, with verification:

```
1. griptape_nodes_GrantPermissionRuleRequest(rule={
     "id": "user.deny-labs-libraries",
     "decision": "deny",
     "reason": "labs-stage libraries are not permitted in this workspace",
     "granted_by": "user",
     "when": {
       "action": {"request_type": {"op": "equals", "value": "RegisterLibraryFromFileRequest"}},
       "context": {"facts": {
         "request.metadata.declarations.lifecycle_stage": {"op": "equals", "value": "LABS"}
       }}
     }
   })
   → returns rule_id="user.deny-labs-libraries".

2. griptape_nodes_GetEffectivePolicyRequest()
   → confirm the rule appears in policy.rules.

3. (User restarts the engine, or attempts to register a LABS library.)

4. griptape_nodes_ListPermissionDecisionsRequest(limit=10)
   → expected: an entry with rule_id="user.deny-labs-libraries",
     decision="deny", action_request_type="RegisterLibraryFromFileRequest".
     If absent, the labs library never reached the dispatcher (check for
     bypass) or the rule didn't match (inspect inspected_paths).
```

If the user later wants to drop the rule:

```
griptape_nodes_RevokePermissionRuleRequest(rule_id="user.deny-labs-libraries")
```

## Further Reading

- [Permissions reference](https://docs.griptapenodes.com/en/stable/permissions/index.md) — full schema, license layer, audit log, settings reference.
- [Bypass audit](https://docs.griptapenodes.com/en/stable/permissions/index.md#limitations) — current dispatcher coverage gaps.
