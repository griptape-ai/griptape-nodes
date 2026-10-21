- A library's nodes can now run on another machine running Griptape Nodes, such as a shared GPU
  machine. List the library with that machine's engine ID in `distributed_execution.libraries`; the
  machine must serve `websocket_direct` at the address in its
  `transports.websocket_direct.advertise_url`. Results, progress, logs, and secret lookups come back
  to the artist's editor.
