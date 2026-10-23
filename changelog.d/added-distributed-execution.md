- A library's nodes can now run on another Griptape Nodes engine, such as one on a shared GPU
  computer. List the library with that engine's ID in `distributed_execution.libraries`.
  The workstation connects to that engine directly when it publishes an address in
  `transports.websocket_direct.advertise_url`, and through Griptape Cloud otherwise. Results,
  progress, logs, and secret lookups come back to the artist's editor.
