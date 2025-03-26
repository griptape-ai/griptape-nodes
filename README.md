# Griptape Nodes Engine

## Getting Started

Review the [CONTRIBUTING.md](CONTRIBUTING.md) file for how to get started with the project.

# API Documentation

Base URL: `http://127.0.0.1:5000/api`

# API Documentation

## Endpoint

**POST** `/request`

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
  "event_type": "EventResult_Success",
  "request_type": "StartFlowRequest",
  "result_type": "StartFlowResult_Success",
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
  "event_type": "EventResult_Failure",
  "request_type": "StartFlowRequest", 
  "result_type": "StartFlowResult_Failure",
  "request": {
    "request_id": 2,
    "flow_name": "canvas",
    "debug_mode": false
  },
  "result": {}
}
```

### Request Types

#### 1. Python Execution Requests

##### Run Arbitrary Python String

- **Request Payload**: `RunArbitraryPythonStringRequest`

  - `python_string`: (string) The Python code to execute

- **Result Success Response**: `RunArbitraryPythonStringResult_Success`

  - `python_output`: (string) Output of the executed Python code

- **Result Failure Response**: `RunArbitraryPythonStringResult_Failure`

  - `python_output`: (string) Error message

#### 2. Configuration Management Requests

##### Get Configuration Value

- **Request Payload**: `GetConfigValueRequest`

  - `category_and_key`: (string) The configuration category and key

- **Result Success Response**: `GetConfigValueResult_Success`

  - `value`: (any) The configuration value

##### Set Configuration Value

- **Request Payload**: `SetConfigValueRequest`
  - `category_and_key`: (string) The configuration category and key
  - `value`: (any) The value to set

##### Get Configuration Category

- **Request Payload**: `GetConfigCategoryRequest`

  - `category`: (optional string) The configuration category to retrieve

- **Result Success Response**: `GetConfigCategoryResult_Success`

  - `contents`: (dictionary[str, Any]) Configuration contents for the specified category

##### Set Configuration Category

- **Request Payload**: `SetConfigCategoryRequest`
  - `contents`: (dictionary[str, Any]) Configuration contents to set
  - `category`: (optional string) The configuration category

#### 3. Connection Management Requests

##### Create Connection

- **Request Payload**: `CreateConnectionRequest`
  - `source_node_name`: (string) Name of the source node
  - `source_parameter_name`: (string) Name of the source parameter
  - `target_node_name`: (string) Name of the target node
  - `target_parameter_name`: (string) Name of the target parameter

##### Delete Connection

- **Request Payload**: `DeleteConnectionRequest`
  - `source_node_name`: (string) Name of the source node
  - `source_parameter_name`: (string) Name of the source parameter
  - `target_node_name`: (string) Name of the target node
  - `target_parameter_name`: (string) Name of the target parameter

##### List Connections for Node

- **Request Payload**: `ListConnectionsForNodeRequest`

  - `node_name`: (string) Name of the node to list connections for

- **Result Success Response**: `ListConnectionsForNodeResult_Success`

  - `incoming_connections`: (list[IncomingConnection]) Incoming connections to the node
    - type of `IncomingConnection`:
      - source_node_name: (string) Name of the source node
      - source_parameter_name: (string) Name of the source parameter
      - target_parameter_name: (string) Name of the target parameter
  - `outgoing_connections`: (list[OutgoingConnection]) Outgoing connections from the node
    - type of `OutgoingConnection`:
      - source_parameter_name: (string) Name of the source parameter
      - target_node_name: (string) Name of the target node
      - target_parameter_name: (string) Name of the target parameter

#### 4. Flow Management Requests

##### Create Flow

- **Request Payload**: `CreateFlowRequest`

  - `parent_flow_name`: (optional string) Name of the parent flow
  - `flow_name`: (optional string) Name of the new flow

- **Result Success Response**: `CreateFlowResult_Success`

  - `flow_name`: (string) Name of the created flow

##### Delete Flow

- **Request Payload**: `DeleteFlowRequest`
  - `flow_name`: (string) Name of the flow to delete

##### List Nodes in Flow

- **Request Payload**: `ListNodesInFlowRequest`

  - `flow_name`: (string) Name of the flow

- **Result Success Response**: `ListNodesInFlowResult_Success`

  - `node_names`: (list[string]) Names of nodes in the flow

##### List Flows in Flow

- **Request Payload**: `ListFlowsInFlowRequest`

  - `parent_flow_name`: (string) Name of the parent flow

- **Result Success Response**: `ListFlowsInFlowResult_Success`

  - `flow_names`: (list) Names of flows in the parent flow

#### 5. Library and Node Management Requests

##### List Registered Libraries

- **Request Payload**: `ListRegisteredLibrariesRequest`

- **Result Success Response**: `ListRegisteredLibrariesResult_Success`

  - `libraries`: (list) Names of registered libraries

##### List Node Types in Library

- **Request Payload**: `ListNodeTypesInLibraryRequest`

  - `library`: (string) Name of the library

- **Result Success Response**: `ListNodeTypesInLibraryResult_Success`

  - `node_types`: (list) Names of node types in the library

##### Get Node Metadata from Library

- **Request Payload**: `GetNodeMetadataFromLibraryRequest`

  - `library`: (string) Name of the library
  - `node_type`: (string) Name of the node type

- **Result Success Response**: `GetNodeMetadataFromLibraryResult_Success`

  - `metadata`: (dictionary) Metadata for the specified node type

#### 6. Node Management Requests

##### Create Node

- **Request Payload**: `CreateNodeRequest`

  - `library_and_node_type`: (string) Library and node type
  - `node_name`: (optional string) Name of the node
  - `override_parent_flow_name`: (optional string) Parent flow name
  - `metadata`: (optional dictionary) Node metadata

- **Result Success Response**: `CreateNodeResult_Success`

  - `node_name`: (string) Name of the created node

##### Delete Node

- **Request Payload**: `DeleteNodeRequest`
  - `node_name`: (string) Name of the node to delete

##### Get Node Resolution State

- **Request Payload**: `GetNodeResolutionStateRequest`

  - `node_name`: (string) Name of the node

- **Result Success Response**: `GetNodeResolutionStateResult_Success`

  - `state`: (string) Current resolution state of the node

##### List Parameters on Node

- **Request Payload**: `ListParametersOnNodeRequest`

  - `node_name`: (string) Name of the node

- **Result Success Response**: `ListParametersOnNodeResult_Success`

  - `parameter_names`: (list) Names of parameters on the node

##### Get Node Metadata

- **Request Payload**: `GetNodeMetadataRequest`

  - `node_name`: (string) Name of the node

- **Result Success Response**: `GetNodeMetadataResult_Success`

  - `metadata`: (dictionary) Metadata of the node

##### Set Node Metadata

- **Request Payload**: `SetNodeMetadataRequest`
  - `node_name`: (string) Name of the node
  - `metadata`: (dictionary) Metadata to set

#### 7. Parameter Management Requests

##### Add Parameter to Node

- **Request Payload**: `AddParameterToNodeRequest`
  - `parameter_name`: (string) Name of the parameter
  - `node_name`: (string) Name of the node
  - `allowed_types`: (list) Allowed types for the parameter
  - `default_value`: (any) Default value for the parameter
  - `tooltip`: (string) Tooltip description
  - Various optional configuration options

##### Remove Parameter from Node

- **Request Payload**: `RemoveParameterFromNodeRequest`
  - `parameter_name`: (string) Name of the parameter
  - `node_name`: (string) Name of the node

##### Set Parameter Value

- **Request Payload**: `SetParameterValueRequest`
  - `parameter_name`: (string) Name of the parameter
  - `node_name`: (string) Name of the node
  - `value`: (any) Value to set

##### Get Parameter Details

- **Request Payload**: `GetParameterDetailsRequest`

  - `parameter_name`: (string) Name of the parameter
  - `node_name`: (string) Name of the node

- **Result Success Response**: `GetParameterDetailsResult_Success`

  - Detailed parameter configuration information

##### Alter Parameter Details

- **Request Payload**: `AlterParameterDetailsRequest`
  - `parameter_name`: (string) Name of the parameter
  - `node_name`: (string) Name of the node
  - Various optional configuration options to modify

##### Get Parameter Value

- **Request Payload**: `GetParameterValueRequest`

  - `parameter_name`: (string) Name of the parameter
  - `node_name`: (string) Name of the node

- **Result Success Response**: `GetParameterValueResult_Success`

  - `data_type`: (string) Data type of the parameter
  - `value`: (any) Current value of the parameter

#### 8. Script Execution Requests

##### Run Script from Scratch

- **Request Payload**: `RunScriptFromScratchRequest`
  - `file_path`: (string) Path to the script file

##### Run Script with Current State

- **Request Payload**: `RunScriptWithCurrentStateRequest`
  - `file_path`: (string) Path to the script file

##### Run Script from Registry

- **Request Payload**: `RunScriptFromRegistryRequest`
  - `script_name`: (string) Name of the script in the registry

#### 9. Flow Execution Requests

##### Resolve Node

- **Request Payload**: `ResolveNodeRequest`
  - `node_name`: (string) Name of the node to resolve
  - `debug_mode`: (boolean) Enable debug mode

##### Start Flow

- **Request Payload**: `StartFlowRequest`

  - `flow_name`: (string) Name of the flow to start
  - `start_node_name`: (string) Name of the starting node
  - `debug_mode`: (boolean) Enable debug mode

- **Result Success Response**: `StartFlowResult_Success`

  - `current_node_name`: (string) Name of the current node

##### Cancel Flow

- **Request Payload**: `CancelFlowRequest`
  - `flow_name`: (string) Name of the flow to cancel

##### Unresolve Flow

- **Request Payload**: `UnresolveFlowRequest`
  - `flow_name`: (string) Name of the flow to unresolve

#### 10. Execution Control Requests

##### Single Execution Step

- **Request Payload**: `SingleExecutionStepRequest`
  - `flow_name`: (string) Name of the flow

##### Single Node Step

- **Request Payload**: `SingleNodeStepRequest`
  - `flow_name`: (string) Name of the flow

##### Continue Execution

- **Request Payload**: `ContinueExecutionStepRequest`
  - `flow_name`: (string) Name of the flow

##### Get Flow State

- **Request Payload**: `GetFlowStateRequest`

  - `flow_name`: (string) Name of the flow

- **Result Success Response**: `GetFlowStateResult_Success`

  - `control_node`: (string) Current control node
  - `resolving_node`: (string or null) Current resolving node

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
