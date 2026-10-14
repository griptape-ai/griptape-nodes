- `ParameterList` takes `item_converters`, which convert each item whether it is set in its own row
  or arrives in a whole list. In a library declaring `engine_version` 0.105.0 or later, a whole
  list a node sets with `set_parameter_value` becomes the list's items, as it does when set by
  request. See [Parameters](docs/development/custom_nodes/parameters.md).
