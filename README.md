# Griptape Nodes Engine

## Getting Started

For getting started with using Griptape Nodes, please visit [griptapenodes.com](https://www.griptapenodes.com/).

## Contributing

If you would like to contribute to the Griptape Nodes Engine, please review the [CONTRIBUTING.md](CONTRIBUTING.md) file.

### Request Structure

All requests follow this general structure:

```json
{
  "event_type": "EventRequest",
  "request_type": "", //Name of the request type, for example CreateNodeRequest
  "request": {
    // Specific request payload based on the operation
    // Optional: "request_id" will be automatically added by the server if not provided
  }
}
```

### Response Structure

Responses follow this structure:

```json
{
    "node_type": "string",
    "override_parent_flow_id": "string"  // optional
}
```

### Responses

#### Success Response

**Code:** `200`

```json
{
    "message": "Request to create node received"
}
```

#### Example Successful Event Response (Start Flow)

```json
{
  "event_type": "EventResultSuccess",
  "request_type": "StartFlowRequest",
  "result_type": "StartFlowResultSuccess",
  "request": {
    "request_id": 1,
    "flow_name": "canvas",
    "debug_mode": false
  },
  "result": {
  }
}
```

#### Example Failure Event Response (Start Flow)

```json
{
  "event_type": "EventResultFailure",
  "request_type": "StartFlowRequest", 
  "result_type": "StartFlowResultFailure",
  "request": {
    "request_id": 2,
    "flow_name": "canvas",
    "debug_mode": false
  },
  "result": {}
}
```

### Request Counter

Each request is assigned a unique `request_id` that increments with each request. This can be used for tracking and reference purposes.

### Request ID Handling

- If no `request_id` is provided in the request, the server will automatically assign one.
- The `request_id` increments for each request during the session.
- The `request_id` can be used for tracking and referencing specific requests.

### Error Handling

The program prints out appropriate error messages.

#### Example Error Response

```json
{
  "message": "Error: 'request' was expected but not found.",
  "status": 400
}
```

#### Example Successful Request Receipt

```json
{
  "message": "Request for event type 'EventRequest' successfully received",
  "request_id": 3,
  "status": 200
}
```

## Running with the Local API

```env
GRIPTAPE_NODES_API_BASE_URL=http://localhost:8001
```
