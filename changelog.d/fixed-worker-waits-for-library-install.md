- A library whose nodes run in a worker process no longer fails every run with a "No module named"
  error after it is first installed, until the engine restarts. When the editor connected while the
  library was still installing its dependencies, its worker started too early to see them.
