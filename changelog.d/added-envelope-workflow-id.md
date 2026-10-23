- A request envelope (`EventRequest`, and each request in an `EventRequestBatch`) now has an optional
  `workflow_id` naming the workflow open in the tab that sent it, beside `request_id` and never
  inside `request`. `EventManager.handle_request` and `ahandle_request` take it as `workflow_id=`
  and echo it on the result envelope. A request that acts on a workflow runs in the open workflow
  it names and fails when that workflow isn't open; requests that report or replace what is open,
  such as `GetWorkflowContextRequest`, ignore it. See
  [Transports](docs/guides/transports.md#sending-requests).
