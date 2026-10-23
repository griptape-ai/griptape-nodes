- `DescribeNodeTypeRequest` takes `compact`, which returns `parameter_specs` and `exec_pins` in
  place of `metadata` and full `parameters`. Each spec is a parameter's name, type and modes, plus
  its accepted input types, output type, default, choices, whether it takes one connection per
  item, and a short note only where they say something. The standard `exec_in`/`exec_out` pins
  become `exec_pins`, and deprecated parameters are left out. Compact descriptions are cached
  until a library is loaded, reloaded or unloaded, or a node type is registered again, so once
  cached an `EventRequestBatch` of compact requests describes a whole library several times faster
  than full ones, at about a quarter of the size.
  [#5919](https://github.com/griptape-ai/griptape-nodes-engine/issues/5919)
