- A library's nodes can now run on another machine running Griptape Nodes, such as a shared GPU
  machine. List the library with that machine's engine ID in `distributed_execution.libraries`.
  The workstation connects to the machine directly when the machine publishes an address in
  `transports.websocket_direct.advertise_url`, and through Griptape Cloud otherwise. Results,
  progress, logs, and secret lookups come back to the artist's editor.
