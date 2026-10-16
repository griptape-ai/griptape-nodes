- Removing or moving an item of a list parameter now updates the list that
  `GetParameterValueRequest` returns, reruns the nodes that read it, and lets the node react, as
  "Path Join" does when it recomputes its output. A node whose library runs in a separate process
  now receives its list inputs instead of an empty list.
