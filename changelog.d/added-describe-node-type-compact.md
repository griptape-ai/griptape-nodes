- `DescribeNodeTypeRequest` takes `compact`, which returns `parameter_specs` in place of full
  `parameters`: each parameter's types, modes, default, choices, whether it takes multiple inputs,
  whether it is deprecated, and a short note cut from its tooltip, with no tooltips or ui_options.
  Compact descriptions are cached until a library is loaded, reloaded or unloaded, or a node type
  is registered again, so once cached an `EventRequestBatch` of compact requests describes a whole
  library several times faster than full ones, at about half the size.
  [#5919](https://github.com/griptape-ai/griptape-nodes-engine/issues/5919)
