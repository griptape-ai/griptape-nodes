- Removing or moving an item of a list parameter now updates the list that
  `GetParameterValueRequest` returns and reruns the nodes that read it. A node whose library runs
  in a separate process now receives its list inputs instead of an empty list.
