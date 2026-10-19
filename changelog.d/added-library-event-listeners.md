- Advanced libraries can return execution and app event listeners from
  `get_execution_event_listeners()` and `get_app_event_listeners()`, for example to log or time
  every node a workflow runs. The engine registers them when the library loads and removes them
  when it unloads. See
  [Watching node runs](docs/development/custom_nodes/advanced_libraries.md#watching-node-runs).
  [#5779](https://github.com/griptape-ai/griptape-nodes-engine/issues/5779)
