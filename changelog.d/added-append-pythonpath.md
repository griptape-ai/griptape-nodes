- Engine processes now read `GTN_APPEND_PYTHONPATH`, a list of folders searched after the engine's
  own packages. Griptape Nodes Desktop passes the launch environment's `PYTHONPATH` this way, so
  studio modules can be imported from nodes without replacing the engine's packages.
