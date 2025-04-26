# Griptape Nodes Scripting

"Retained Mode" is a Python scripting interface to interact with Griptape Nodes. These methods allow users to create, modify, and manage nodes, parameters, connections, and flows through a simplified Python API.

> **Note:** The actual import command for RetainedMode is:
>
> ```python
> from griptape_nodes.retained_mode import RetainedMode as cmd
> ```
>
> However, for convenience, in the script editor of the GUI, this import is already done for you automatically, so you can freely use `cmd.` directly.

## Go to:

[Flow Operations](#flow-operations) · [Node Operations](#node-operations) · [Parameter Operations](#parameter-operations) · [Connection Operations](#connection-operations) · [Library Operations](#library-operations) · [Config Operations](#config-operations) · [Utility Operations](#utility-operations)

## Flow Operations

### create_flow

```python
cmd.create_flow(flow_name=None, parent_flow_name=None)
```

Creates a new flow within the Griptape system.

#### Arguments

| Name             | Argument Type | Required |
| ---------------- | :-----------: | :------: |
| flow_name        |    string     |    ⚪    |
| parent_flow_name |    string     |    ⚪    |

#### Return Value

ResultPayload object with flow creation status

#### Description

Creates a new flow with the specified name. If parent_flow_name is provided, the new flow will be created as a child of the specified parent flow.

______________________________________________________________________

### delete_flow

```python
cmd.delete_flow(flow_name)
```

Deletes an existing flow.

#### Arguments

| Name      | Argument Type | Required |
| --------- | :-----------: | :------: |
| flow_name |    string     |    🟢    |

#### Return Value

ResultPayload object with flow deletion status

#### Description

Removes the specified flow from the system.

______________________________________________________________________

### get_flows

```python
cmd.get_flows(parent_flow_name=None)
```

Lists all flows within a parent flow.

#### Arguments

| Name             | Argument Type | Required |
| ---------------- | :-----------: | :------: |
| parent_flow_name |    string     |    ⚪    |

#### Return Value

ResultPayload object containing a list of flows

#### Description

Returns all flows within the specified parent flow. If no parent_flow_name is provided, returns all top-level flows.

______________________________________________________________________

### get_nodes_in_flow

```python
cmd.get_nodes_in_flow(flow_name)
```

Lists all nodes within a flow.

#### Arguments

| Name      | Argument Type | Required |
| --------- | :-----------: | :------: |
| flow_name |    string     |    🟢    |

#### Return Value

ResultPayload object containing a list of node names

#### Description

Returns all nodes within the specified flow.

______________________________________________________________________

### run_flow

```python
cmd.run_flow(flow_name)
```

Executes a flow.

#### Arguments

| Name      | Argument Type | Required |
| --------- | :-----------: | :------: |
| flow_name |    string     |    🟢    |

#### Return Value

ResultPayload object with flow execution status

#### Description

Starts the execution of the specified flow.

______________________________________________________________________

### reset_flow

```python
cmd.reset_flow(flow_name)
```

Resets a flow to its initial state.

#### Arguments

| Name      | Argument Type | Required |
| --------- | :-----------: | :------: |
| flow_name |    string     |    🟢    |

#### Return Value

ResultPayload object with flow reset status

#### Description

Unresolves all nodes in the flow, returning it to its initial state.

______________________________________________________________________

### get_flow_state

```python
cmd.get_flow_state(flow_name)
```

Returns the current state of a flow.

#### Arguments

| Name      | Argument Type | Required |
| --------- | :-----------: | :------: |
| flow_name |    string     |    🟢    |

#### Return Value

ResultPayload object containing flow state information

#### Description

Gets the current execution state of the specified flow.

______________________________________________________________________

### cancel_flow

```python
cmd.cancel_flow(flow_name)
```

Cancels the execution of a flow.

#### Arguments

| Name      | Argument Type | Required |
| --------- | :-----------: | :------: |
| flow_name |    string     |    🟢    |

#### Return Value

ResultPayload object with flow cancellation status

#### Description

Stops the execution of the specified flow.

______________________________________________________________________

### single_step

```python
cmd.single_step(flow_name)
```

Executes a single node step in a flow.

#### Arguments

| Name      | Argument Type | Required |
| --------- | :-----------: | :------: |
| flow_name |    string     |    🟢    |

#### Return Value

ResultPayload object with step execution status

#### Description

Executes a single node in the specified flow.

______________________________________________________________________

### single_execution_step

```python
cmd.single_execution_step(flow_name)
```

Executes a single execution step in a flow.

#### Arguments

| Name      | Argument Type | Required |
| --------- | :-----------: | :------: |
| flow_name |    string     |    🟢    |

#### Return Value

ResultPayload object with execution step status

#### Description

Executes a single execution step in the specified flow.

______________________________________________________________________

### continue_flow

```python
cmd.continue_flow(flow_name)
```

Continues the execution of a paused flow.

#### Arguments

| Name      | Argument Type | Required |
| --------- | :-----------: | :------: |
| flow_name |    string     |    🟢    |

#### Return Value

ResultPayload object with flow continuation status

#### Description

Continues the execution of a flow that was previously paused.

## Node Operations

### create_node

```python
cmd.create_node(node_type, specific_library_name=None, node_name=None, parent_flow_name=None, metadata=None)
```

Creates a new node.

#### Arguments

| Name                  | Argument Type | Required |
| --------------------- | :-----------: | :------: |
| node_type             |    string     |    🟢    |
| specific_library_name |    string     |    ⚪    |
| node_name             |    string     |    ⚪    |
| parent_flow_name      |    string     |    ⚪    |
| metadata              |     dict      |    ⚪    |

#### Return Value

Node name or ResultPayload object with node creation status

#### Description

Creates a new node of the specified type. Optional parameters allow specifying the library, node name, parent flow, and metadata.

______________________________________________________________________

### delete_node

```python
cmd.delete_node(node_name)
```

Deletes an existing node.

#### Arguments

| Name      | Argument Type | Required |
| --------- | :-----------: | :------: |
| node_name |    string     |    🟢    |

#### Return Value

ResultPayload object with node deletion status

#### Description

Removes the specified node from the system.

______________________________________________________________________

### run_node

```python
cmd.run_node(node_name)
```

Executes a single node.

#### Arguments

| Name      | Argument Type | Required |
| --------- | :-----------: | :------: |
| node_name |    string     |    🟢    |

#### Return Value

ResultPayload object with node execution status

#### Description

Resolves and executes the specified node.

______________________________________________________________________

### get_resolution_state_for_node

```python
cmd.get_resolution_state_for_node(node_name)
```

Returns the resolution state of a node.

#### Arguments

| Name      | Argument Type | Required |
| --------- | :-----------: | :------: |
| node_name |    string     |    🟢    |

#### Return Value

ResultPayload object containing node resolution state

#### Description

Gets the current resolution state of the specified node.

______________________________________________________________________

### get_metadata_for_node

```python
cmd.get_metadata_for_node(node_name)
```

Returns the metadata for a node.

#### Arguments

| Name      | Argument Type | Required |
| --------- | :-----------: | :------: |
| node_name |    string     |    🟢    |

#### Return Value

ResultPayload object containing node metadata

#### Description

Gets the metadata associated with the specified node.

______________________________________________________________________

### set_metadata_for_node

```python
cmd.set_metadata_for_node(node_name, metadata)
```

Sets the metadata for a node.

#### Arguments

| Name      | Argument Type | Required |
| --------- | :-----------: | :------: |
| node_name |    string     |    🟢    |
| metadata  |     dict      |    🟢    |

#### Return Value

ResultPayload object with metadata update status

#### Description

Sets the metadata for the specified node.

______________________________________________________________________

### exists

```python
cmd.exists(node)
```

Checks if a node exists.

#### Arguments

| Name | Argument Type | Required |
| ---- | :-----------: | :------: |
| node |    string     |    🟢    |

#### Return Value

Boolean indicating whether the node exists

#### Description

Returns True if the specified node exists, False otherwise.

______________________________________________________________________

### ls

```python
cmd.ls(**kwargs)
```

Lists objects in the system.

#### Arguments

| Name       | Argument Type | Required |
| ---------- | :-----------: | :------: |
| \*\*kwargs |     dict      |    ⚪    |

#### Return Value

List of object names matching the filter criteria

#### Description

Lists objects in the system, optionally filtered by the provided criteria.

## Parameter Operations

### list_params

```python
cmd.list_params(node)
```

Lists all parameters on a node.

#### Arguments

| Name | Argument Type | Required |
| ---- | :-----------: | :------: |
| node |    string     |    🟢    |

#### Return Value

List of parameter names

#### Description

Returns a list of all parameters on the specified node.

______________________________________________________________________

### add_param

```python
cmd.add_param(node_name, parameter_name, default_value, tooltip, type=None, input_types=None, output_type=None, edit=False, tooltip_as_input=None, tooltip_as_property=None, tooltip_as_output=None, ui_options=None, mode_allowed_input=True, mode_allowed_property=True, mode_allowed_output=True, **kwargs)
```

Adds a parameter to a node.

#### Arguments

| Name                  |   Argument Type    | Required |
| --------------------- | :----------------: | :------: |
| node_name             |       string       |    🟢    |
| parameter_name        |       string       |    🟢    |
| default_value         |        any         |    🟢    |
| tooltip               |   string or list   |    🟢    |
| type                  |       string       |    ⚪    |
| input_types           |  list of strings   |    ⚪    |
| output_type           |       string       |    ⚪    |
| edit                  |      boolean       |    ⚪    |
| tooltip_as_input      |   string or list   |    ⚪    |
| tooltip_as_property   |   string or list   |    ⚪    |
| tooltip_as_output     |   string or list   |    ⚪    |
| ui_options            | ParameterUIOptions |    ⚪    |
| mode_allowed_input    |      boolean       |    ⚪    |
| mode_allowed_property |      boolean       |    ⚪    |
| mode_allowed_output   |      boolean       |    ⚪    |

#### Return Value

ResultPayload object with parameter addition status

#### Description

Adds a parameter to the specified node with the given configuration. If edit=True, modifies an existing parameter instead.

______________________________________________________________________

### del_param

```python
cmd.del_param(node_name, parameter_name)
```

Removes a parameter from a node.

#### Arguments

| Name           | Argument Type | Required |
| -------------- | :-----------: | :------: |
| node_name      |    string     |    🟢    |
| parameter_name |    string     |    🟢    |

#### Return Value

ResultPayload object with parameter removal status

#### Description

Removes the specified parameter from the node.

______________________________________________________________________

### param_info

```python
cmd.param_info(node, param) or cmd.param_info("node.param")
```

Gets information about a parameter.

#### Arguments

| Name  | Argument Type | Required |
| ----- | :-----------: | :------: |
| node  |    string     |    🟢    |
| param |    string     |    🟢    |

#### Return Value

ResultPayload object containing parameter details

#### Description

Returns detailed information about the specified parameter. Accepts either separate node and param arguments or a single "node.param" string.

______________________________________________________________________

### get_value

```python
cmd.get_value(node, param) or cmd.get_value("node.param")
```

Gets the value of a parameter.

#### Arguments

| Name  | Argument Type | Required |
| ----- | :-----------: | :------: |
| node  |    string     |    🟢    |
| param |    string     |    🟢    |

#### Return Value

The value of the parameter or a failure result

#### Description

Returns the current value of the specified parameter. Supports indexed access for container types (e.g., "node.param[0]").

______________________________________________________________________

### set_value

```python
cmd.set_value(node, param, value) or cmd.set_value("node.param", value)
```

Sets the value of a parameter.

#### Arguments

| Name  | Argument Type | Required |
| ----- | :-----------: | :------: |
| node  |    string     |    🟢    |
| param |    string     |    🟢    |
| value |      any      |    🟢    |

#### Return Value

ResultPayload object with value update status

#### Description

Sets the value of the specified parameter. Supports indexed access for container types (e.g., "node.param[0]").

## Connection Operations

### connect

```python
cmd.connect(source, destination)
```

Creates a connection between two parameters.

#### Arguments

| Name        | Argument Type | Required |
| ----------- | :-----------: | :------: |
| source      |    string     |    🟢    |
| destination |    string     |    🟢    |

#### Return Value

ResultPayload object with connection creation status

#### Description

Creates a connection from the source parameter to the destination parameter. Both arguments should be in the format "node.param".

______________________________________________________________________

### exec_chain

```python
cmd.exec_chain(*node_names)
```

Creates execution connections between a sequence of nodes.

#### Arguments

| Name         | Argument Type | Required |
| ------------ | :-----------: | :------: |
| \*node_names |   string(s)   |    🟢    |

#### Return Value

Dictionary with results of each connection attempt

#### Description

Creates exec_out -> exec_in connections between a sequence of nodes, effectively chaining them for execution in sequence.

______________________________________________________________________

### delete_connection

```python
cmd.delete_connection(source_node_name, source_param_name, target_node_name, target_param_name)
```

Deletes a connection between parameters.

#### Arguments

| Name              | Argument Type | Required |
| ----------------- | :-----------: | :------: |
| source_node_name  |    string     |    🟢    |
| source_param_name |    string     |    🟢    |
| target_node_name  |    string     |    🟢    |
| target_param_name |    string     |    🟢    |

#### Return Value

ResultPayload object with connection deletion status

#### Description

Removes the connection between the specified source and target parameters.

______________________________________________________________________

### get_connections_for_node

```python
cmd.get_connections_for_node(node_name)
```

Lists all connections for a node.

#### Arguments

| Name      | Argument Type | Required |
| --------- | :-----------: | :------: |
| node_name |    string     |    🟢    |

#### Return Value

ResultPayload object containing connection information

#### Description

Returns all connections involving the specified node, both incoming and outgoing.

## Library Operations

### get_available_libraries

```python
cmd.get_available_libraries()
```

Lists all available node libraries.

#### Arguments

None

#### Return Value

ResultPayload object containing a list of library names

#### Description

Returns all registered node libraries in the system.

______________________________________________________________________

### get_node_types_in_library

```python
cmd.get_node_types_in_library(library_name)
```

Lists all node types in a library.

#### Arguments

| Name         | Argument Type | Required |
| ------------ | :-----------: | :------: |
| library_name |    string     |    🟢    |

#### Return Value

ResultPayload object containing a list of node type names

#### Description

Returns all node types available in the specified library.

______________________________________________________________________

### get_node_metadata_from_library

```python
cmd.get_node_metadata_from_library(library_name, node_type_name)
```

Gets metadata for a node type.

#### Arguments

| Name           | Argument Type | Required |
| -------------- | :-----------: | :------: |
| library_name   |    string     |    🟢    |
| node_type_name |    string     |    🟢    |

#### Return Value

ResultPayload object containing node type metadata

#### Description

Returns the metadata for the specified node type in the given library.

## Config Operations

### get_config_value

```python
cmd.get_config_value(category_and_key)
```

Gets a configuration value.

#### Arguments

| Name             | Argument Type | Required |
| ---------------- | :-----------: | :------: |
| category_and_key |    string     |    🟢    |

#### Return Value

ResultPayload object containing the configuration value

#### Description

Returns the value for the specified configuration key.

______________________________________________________________________

### set_config_value

```python
cmd.set_config_value(category_and_key, value)
```

Sets a configuration value.

#### Arguments

| Name             | Argument Type | Required |
| ---------------- | :-----------: | :------: |
| category_and_key |    string     |    🟢    |
| value            |      any      |    🟢    |

#### Return Value

ResultPayload object with configuration update status

#### Description

Sets the value for the specified configuration key.

______________________________________________________________________

### get_config_category

```python
cmd.get_config_category(category=None)
```

Gets all configuration values in a category.

#### Arguments

| Name     | Argument Type | Required |
| -------- | :-----------: | :------: |
| category |    string     |    ⚪    |

#### Return Value

ResultPayload object containing category configuration values

#### Description

Returns all configuration values in the specified category. If no category is provided, returns all configuration values.

______________________________________________________________________

### set_config_category

```python
cmd.set_config_category(category=None, contents={})
```

Sets configuration values for a category.

#### Arguments

| Name     | Argument Type | Required |
| -------- | :-----------: | :------: |
| category |    string     |    ⚪    |
| contents |     dict      |    ⚪    |

#### Return Value

ResultPayload object with category configuration update status

#### Description

Sets all configuration values for the specified category with the provided contents.

## Utility Operations

### run_arbitrary_python

```python
cmd.run_arbitrary_python(python_str)
```

Executes arbitrary Python code.

#### Arguments

| Name       | Argument Type | Required |
| ---------- | :-----------: | :------: |
| python_str |    string     |    🟢    |

#### Return Value

ResultPayload object with execution status and results

#### Description

Executes the provided Python code string in the Griptape environment.

## Examples

### Creating a Flow and Nodes

```python
# Create a new flow
flow = cmd.create_flow(flow_name="MyFlow")

# Create two nodes in the flow
node1 = cmd.create_node(node_type="CreateText", node_name="MyText", parent_flow_name="MyFlow")
node2 = cmd.create_node(node_type="RunAgent", node_name="MyAgent", parent_flow_name="MyFlow")
```

### Setting Parameter Values and Creating Connections

```python
# Set a parameter value
cmd.set_value("MyText.text", "This is a sample text to summarize.")

# Connect two nodes
cmd.connect("MyText.text", "MyAgent.prompt")

```

### Running a Flow

```python
# Run the flow
cmd.run_flow("MyFlow")

# Get the result
summary = cmd.get_value("MyAgent.output")
print(summary) # <whatever that summary would be!>
```

### Working with Parameters

```python
# Add a new parameter to a node
cmd.add_param(
    node_name="MyAgent",
    parameter_name="sunglasses",
    default_value=100,
    tooltip="The coolness of sunglasses",
    type=["int"]
)

# Set the value of the new parameter
cmd.set_value("MyAgent.sunglasses", 50)

# Change the parameter
cmd.add_param(
    node_name="MyAgent",
    parameter_name="sunglasses",
    tooltip="The coolness of sunglasses if halved",
    edit=1
)
```

### Listing and Querying

```python
# List all nodes in a flow
nodes = cmd.get_nodes_in_flow("MyFlow")
print(nodes) # ["MyText","MyAgent"]

# List all parameters on a node
params = cmd.list_params("MyAgent")
print(params) # ["agent", "prompt_driver", "tools", "rulesets", "prompt", "prompt_context", "output"]

# Check if a node exists
if cmd.exists("MyText"):
    print("MyText node exists") # True
```
