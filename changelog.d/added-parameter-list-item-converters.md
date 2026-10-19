- `ParameterList` takes `item_converters`, which convert each item whether it is set in its own row
  or arrives in a whole list. A whole list a node sets on its own list with `set_parameter_value`
  now becomes the list's items, as it does when set by request. See
  [Parameters](docs/development/custom_nodes/parameters.md).
