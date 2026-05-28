# `EventRequestBatch` MCP tool: Claude refuses to populate args

## TL;DR

Claude (Anthropic) on Griptape Cloud calls `GriptapeNodes_EventRequestBatch`
with empty arguments, repeatedly, and Pydantic AI ends the run with
`UnexpectedModelBehavior: Tool ... exceeded max retries count`. GPT-4o on the
same endpoint, with the same schema, calls the tool fine.

The cause is the tool's JSON Schema, not prompting. Fix the schema; the rest
takes care of itself.

## Where it shows up

```
INFO  griptape_nodes: tool call #5 -> GriptapeNodes_EventRequestBatch(<empty: ''>) id=toolu_...
INFO  griptape_nodes: tool result <- ... preview="Input validation error: 'requests' is a required property" is_error=True
INFO  griptape_nodes: tool call #6 -> GriptapeNodes_EventRequestBatch(<empty: ''>) id=toolu_...
INFO  griptape_nodes: tool result <- ... preview="Input validation error: 'requests' is a required property" is_error=True
...
ERROR  Tool 'GriptapeNodes_EventRequestBatch' exceeded max retries count of 3
```

## Root cause

The schema lives in `src/griptape_nodes/servers/mcp.py::_event_request_batch_input_schema`:

```python
{
    "type": "object",
    "properties": {
        "requests": {
            "type": "array", "minItems": 1,
            "items": {
                "type": "object",
                "properties": {
                    "request_type": {"type": "string", "enum": [...30+ values...]},
                    "request": {                         # <-- the problem
                        "type": "object",
                        "additionalProperties": True,
                        # No `properties`. Shape depends on the `request_type` sibling.
                    },
                },
                "required": ["request_type", "request"],
            },
        },
        "timeout_ms": {"type": "integer", "minimum": 1},
    },
    "required": ["requests"],
}
```

The inner `request` is intentionally free-form because its real shape is
selected by `request_type`. JSON Schema's standard answer for this is a
discriminated `oneOf`; ours just punts and accepts any object.

Empirical Anthropic behavior with this schema:

- Simple schemas (e.g. `add(a: int, b: int)`) -> Claude streams JSON args fine.
- This schema -> Claude emits one streaming chunk with `partial_input: ""`,
  nothing else, and stops. The MCP SDK's built-in JSON Schema validator
  (`mcp/server/lowlevel/server.py:530`) rejects the empty arg dict for missing
  `requests`, the failure becomes a `ModelRetry`, Claude retries with the same
  empty args, the retry counter climbs, the run dies.

It is documented Anthropic behavior that tool-use mode is conservative on
underspecified schemas: if the model can't generate args confidently, it sends
empty rather than guessing. This is the exact failure here.

## What did NOT fix it

Logged for the next person so they don't burn time:

1. Bumping `max_retries` from 1 to 3 on the MCP server. Claude makes the same
   mistake every time; more retries just take longer to fail.
2. Adding inline JSON examples and a `REQUIRED` directive to the tool's
   `description` field. Claude reads schema *shape* first; prose second.
3. Adding the JSON Schema `examples` array at the top level. Anthropic does
   not appear to use it for tool-arg generation.
4. Loading a workspace skill (`.agents/skills/griptape-nodes-workflows/SKILL.md`)
   that explicitly demonstrates `EventRequestBatch` usage. Claude reads it but
   doesn't use it to override the schema-driven decision to send empty args.
5. Setting `additionalProperties: true` explicitly on the inner `request`
   field. No-op against this failure mode.

The agent harness work landed regardless of this issue and is fine; this is a
Claude-vs-this-specific-schema problem, not a harness problem. Other models
(GPT-4o, Gemini) call the tool with populated args.

## The fix: `oneOf` discriminated union per `request_type`

Replace the current schema's `items` with a `oneOf` whose branches are
generated from `SUPPORTED_REQUEST_EVENTS`:

```python
"items": {
    "oneOf": [
        {
            "type": "object",
            "properties": {
                "request_type": {"const": name},
                "request": <schema for that RequestPayload>,
            },
            "required": ["request_type", "request"],
        }
        for name, payload_cls in SUPPORTED_REQUEST_EVENTS.items()
    ],
}
```

Where `<schema for that RequestPayload>` is what `pydantic.TypeAdapter(payload_cls).json_schema()`
already returns. We use that for the single-request tools; reuse it here.

Notes for whoever picks this up:

- `SUPPORTED_REQUEST_EVENTS` lives at the top of `src/griptape_nodes/servers/mcp.py`.
  Each value is a `RequestPayload` dataclass.
- `pydantic.TypeAdapter(event).json_schema()` is the same call used in
  `list_tools()` to expose single-request tools, so the per-branch schemas are
  free.
- The `request_type` branch should use `"const": name` (or `"enum": [name]`),
  not `"type": "string"`. That's how Claude knows which branch matches.
- Keep the existing server-side dataclass instantiation in `_build_batch_pairs`
  as a defense-in-depth check; the MCP SDK's `jsonschema.validate` will catch
  most shape errors before we get there, but malformed JSON still slips through.
- Watch the schema size. With 30+ request types each carrying their full
  dataclass schema, the resulting schema gets large. If the GTC chat-messages
  endpoint or Anthropic's tool-use API truncates above some size, we may need
  to slim down (e.g. drop the `broadcast_result`/`request_id`/`failure_log_level`
  fields that Pydantic generates from the base class).
- `examples` and the long `description` we added in the previous attempt can
  stay or go; with a typed `oneOf` they're nice-to-have, not load-bearing.

## Acceptance test

Re-run a meme-maker-style chat-sidebar prompt against Claude on Griptape
Cloud through `make run`. The `[run X] tool call #N -> GriptapeNodes_EventRequestBatch(...)`
log line should show populated args (e.g. `{requests=...}`) on the first try.
The whole run should complete without the `UnexpectedModelBehavior` error.

GPT-4o should keep working too — it already does, but cycle through both to
make sure the new schema doesn't regress.

## Pointers

| What | Where |
|---|---|
| MCP tool schema | `src/griptape_nodes/servers/mcp.py::_event_request_batch_input_schema` |
| Tool description | `src/griptape_nodes/servers/mcp.py::EVENT_REQUEST_BATCH_DESCRIPTION` |
| Server-side dispatch | `src/griptape_nodes/servers/mcp.py::call_tool` (`if name == EVENT_REQUEST_BATCH_TOOL_NAME`) |
| Server-side validation | `src/griptape_nodes/servers/mcp.py::_build_batch_pairs` |
| MCP SDK validator | `.venv/lib/python3.12/site-packages/mcp/server/lowlevel/server.py:530` |
| Single-request schema source | `pydantic.TypeAdapter(payload_cls).json_schema()` |
| Agent log format | `[run X] tool call #N -> <Tool>(<args-or-empty>) id=...` |
