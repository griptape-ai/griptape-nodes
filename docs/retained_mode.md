# Griptape RetainedMode Command Reference

## Go to: [Flow Operations](#flow-operations) · [Node Operations](#node-operations) · [Parameter Operations](#parameter-operations) · [Connection Operations](#connection-operations) · [Library Operations](#library-operations) · [Config Operations](#config-operations) · [Utility Operations](#utility-operations)

## Synopsis

The RetainedMode class provides a surface-level scripting interface to interact with the Griptape Nodes framework. These methods allow users to create, modify, and manage nodes, parameters, connections, and flows through a simplified Python API.

## Flow Operations

### create_flow

```python
RetainedMode.create_flow(flow_name=None, parent_flow_name=None)
```

Creates a new flow within the Griptape system.

#### Arguments

| Long Name | Short Name | Argument Type | Properties |
|-----------|------------|---------------|------------|
| flow_name | None | string | |
| parent_flow_name | None | string | |

Default: None

#### Return Value
ResultPayload object with flow creation status

#### Description
Creates a new flow with the specified name. If parent_flow_name is provided, the new flow will be created as a child of the specified parent flow.

---

### delete_flow

```python
RetainedMode.delete_flow(flow_name)
```

Deletes an existing flow.

#### Arguments

| Long Name | Short Name | Argument Type | Properties |
|-----------|------------|---------------|------------|
| flow_name | None | string | |

#### Return Value
ResultPayload object with flow deletion status

#### Description
Removes the specified flow from the system.

---

### get_flows

```python
RetainedMode.get_flows(parent_flow_name=None)
```

Lists all flows within a parent flow.

#### Arguments

| Long Name | Short Name | Argument Type | Properties |
|-----------|------------|---------------|------------|
| parent_flow_name | None | string | |

Default: None

#### Return Value
ResultPayload object containing a list of flows

#### Description
Returns all flows within the specified parent flow. If no parent_flow_name is provided, returns all top-level flows.

---

### get_nodes_in_flow

```python
RetainedMode.get_nodes_in_flow(flow_name)
```

Lists all nodes within a flow.

#### Arguments

| Long Name | Short Name | Argument Type | Properties |
|-----------|------------|---------------|------------|
| flow_name | None | string | |

#### Return Value
ResultPayload object containing a list of node names

#### Description
Returns all nodes within the specified flow.

---

### run_flow

```python
RetainedMode.run_flow(flow_name)
```

Executes a flow.

#### Arguments

| Long Name | Short Name | Argument Type | Properties |
|-----------|------------|---------------|------------|
| flow_name | None | string | |

#### Return Value
ResultPayload object with flow execution status

#### Description
Starts the execution of the specified flow.

---

### reset_flow

```python
RetainedMode.reset_flow(flow_name)
```

Resets a flow to its initial state.

#### Arguments

| Long Name | Short Name | Argument Type | Properties |
|-----------|------------|---------------|------------|
| flow_name | None | string | |

#### Return Value
ResultPayload object with flow reset status

#### Description
Unresolves all nodes in the flow, returning it to its initial state.

---

### get_flow_state

```python
RetainedMode.get_flow_state(flow_name)
```

Returns the current state of a flow.

#### Arguments

| Long Name | Short Name | Argument Type | Properties |
|-----------|------------|---------------|------------|
| flow_name | None | string | |

#### Return Value
ResultPayload object containing flow state information

#### Description
Gets the current execution state of the specified flow.

---

### cancel_flow

```python
RetainedMode.cancel_flow(flow_name)
```

Cancels the execution of a flow.

#### Arguments

| Long Name | Short Name | Argument Type | Properties |
|-----------|------------|---------------|------------|
| flow_name | None | string | |

#### Return Value
ResultPayload object with flow cancellation status

#### Description
Stops the execution of the specified flow.

---

### single_step

```python
RetainedMode.single_step(flow_name)
```

Executes a single node step in a flow.

#### Arguments

| Long Name | Short Name | Argument Type | Properties |
|-----------|------------|---------------|------------|
| flow_name | None | string | |

#### Return Value
ResultPayload object with step execution status

#### Description
Executes a single node in the specified flow.

---

### single_execution_step

```python
RetainedMode.single_execution_step(flow_name)
```

Executes a single execution step in a flow.

#### Arguments

| Long Name | Short Name | Argument Type | Properties |
|-----------|------------|---------------|------------|
| flow_name | None | string | |

#### Return Value
ResultPayload object with execution step status

#### Description
Executes a single execution step in the specified flow.

---

### continue_flow

```python
RetainedMode.continue_flow(flow_name)
```

Continues the execution of a paused flow.

#### Arguments

| Long Name | Short Name | Argument Type | Properties |
|-----------|------------|---------------|------------|
| flow_name | None | string | |

#### Return Value
ResultPayload object with flow continuation status

#### Description
Continues the execution of a flow that was previously paused.

## Node Operations

### create_node

```python
RetainedMode.create_node(node_type, specific_library_name=None, node_name=None, parent_flow_name=None, metadata=None)
```

Creates a new node.

#### Arguments

| Long Name | Short Name | Argument Type | Properties |
|-----------|------------|---------------|------------|
| node_type | None | string | |
| specific_library_name | None | string | |
| node_name | None | string | |
| parent_flow_name | None | string | |
| metadata | None | dict | |

Default: None for optional arguments

#### Return Value
Node name or ResultPayload object with node creation status

#### Description
Creates a new node of the specified type. Optional parameters allow specifying the library, node name, parent flow, and metadata.

---

### delete_node

```python
RetainedMode.delete_node(node_name)
```

Deletes an existing node.

#### Arguments

| Long Name | Short Name | Argument Type | Properties |
|-----------|------------|---------------|------------|
| node_name | None | string | |

#### Return Value
ResultPayload object with node deletion status

#### Description
Removes the specified node from the system.

---

### run_node

```python
RetainedMode.run_node(node_name)
```

Executes a single node.

#### Arguments

| Long Name | Short Name | Argument Type | Properties |
|-----------|------------|---------------|------------|
| node_name | None | string | |

#### Return Value
ResultPayload object with node execution status

#### Description
Resolves and executes the specified node.

---

### get_resolution_state_for_node

```python
RetainedMode.get_resolution_state_for_node(node_name)
```

Returns the resolution state of a node.

#### Arguments

| Long Name | Short Name | Argument Type | Properties |
|-----------|------------|---------------|------------|
| node_name | None | string | |

#### Return Value
ResultPayload object containing node resolution state

#### Description
Gets the current resolution state of the specified node.

---

### get_metadata_for_node

```python
RetainedMode.get_metadata_for_node(node_name)
```

Returns the metadata for a node.

#### Arguments

| Long Name | Short Name | Argument Type | Properties |
|-----------|------------|---------------|------------|
| node_name | None | string | |

#### Return Value
ResultPayload object containing node metadata

#### Description
Gets the metadata associated with the specified node.

---

### set_metadata_for_node

```python
RetainedMode.set_metadata_for_node(node_name, metadata)
```

Sets the metadata for a node.

#### Arguments

| Long Name | Short Name | Argument Type | Properties |
|-----------|------------|---------------|------------|
| node_name | None | string | |
| metadata | None | dict | |

#### Return Value
ResultPayload object with metadata update status

#### Description
Sets the metadata for the specified node.

---

### exists

```python
RetainedMode.exists(node)
```

Checks if a node exists.

#### Arguments

| Long Name | Short Name | Argument Type | Properties |
|-----------|------------|---------------|------------|
| node | None | string | |

#### Return Value
Boolean indicating whether the node exists

#### Description
Returns True if the specified node exists, False otherwise.

---

### ls

```python
RetainedMode.ls(**kwargs)
```

Lists objects in the system.

#### Arguments

| Long Name | Short Name | Argument Type | Properties |
|-----------|------------|---------------|------------|
| **kwargs | None | dict | |

#### Return Value
List of object names matching the filter criteria

#### Description
Lists objects in the system, optionally filtered by the provided criteria.

## Parameter Operations

### list_params

```python
RetainedMode.list_params(node)
```

Lists all parameters on a node.

#### Arguments

| Long Name | Short Name | Argument Type | Properties |
|-----------|------------|---------------|------------|
| node | None | string | |

#### Return Value
List of parameter names

#### Description
Returns a list of all parameters on the specified node.

---

### add_param

```python
RetainedMode.add_param(node_name, parameter_name, default_value, tooltip, type=None, input_types=None, output_type=None, edit=False, tooltip_as_input=None, tooltip_as_property=None, tooltip_as_output=None, ui_options=None, mode_allowed_input=True, mode_allowed_property=True, mode_allowed_output=True, **kwargs)
```

Adds a parameter to a node.

#### Arguments

| Long Name | Short Name | Argument Type | Properties |
|-----------|------------|---------------|------------|
| node_name | None | string | |
| parameter_name | None | string | |
| default_value | None | any | |
| tooltip | None | string or list | |
| type | None | string | |
| input_types | None | list of strings | |
| output_type | None | string | |
| edit | None | boolean | |
| tooltip_as_input | None | string or list | |
| tooltip_as_property | None | string or list | |
| tooltip_as_output | None | string or list | |
| ui_options | None | ParameterUIOptions | |
| mode_allowed_input | None | boolean | True |
| mode_allowed_property | None | boolean | True |
| mode_allowed_output | None | boolean | True |

Default: None for most optional arguments, True for boolean flags

#### Return Value
ResultPayload object with parameter addition status

#### Description
Adds a parameter to the specified node with the given configuration. If edit=True, modifies an existing parameter instead.

---

### del_param

```python
RetainedMode.del_param(node_name, parameter_name)
```

Removes a parameter from a node.

#### Arguments

| Long Name | Short Name | Argument Type | Properties |
|-----------|------------|---------------|------------|
| node_name | None | string | |
| parameter_name | None | string | |

#### Return Value
ResultPayload object with parameter removal status

#### Description
Removes the specified parameter from the node.

---

### param_info

```python
RetainedMode.param_info(node, param) or RetainedMode.param_info("node.param")
```

Gets information about a parameter.

#### Arguments

| Long Name | Short Name | Argument Type | Properties |
|-----------|------------|---------------|------------|
| node | None | string | |
| param | None | string | |

#### Return Value
ResultPayload object containing parameter details

#### Description
Returns detailed information about the specified parameter. Accepts either separate node and param arguments or a single "node.param" string.

---

### get_value

```python
RetainedMode.get_value(node, param) or RetainedMode.get_value("node.param")
```

Gets the value of a parameter.

#### Arguments

| Long Name | Short Name | Argument Type | Properties |
|-----------|------------|---------------|------------|
| node | None | string | |
| param | None | string | |

#### Return Value
The value of the parameter or a failure result

#### Description
Returns the current value of the specified parameter. Supports indexed access for container types (e.g., "node.param[0]").

---

### set_value

```python
RetainedMode.set_value(node, param, value) or RetainedMode.set_value("node.param", value)
```

Sets the value of a parameter.

#### Arguments

| Long Name | Short Name | Argument Type | Properties |
|-----------|------------|---------------|------------|
| node | None | string | |
| param | None | string | |
| value | None | any | |

#### Return Value
ResultPayload object with value update status

#### Description
Sets the value of the specified parameter. Supports indexed access for container types (e.g., "node.param[0]").

## Connection Operations

### connect

```python
RetainedMode.connect(source, destination)
```

Creates a connection between two parameters.

#### Arguments

| Long Name | Short Name | Argument Type | Properties |
|-----------|------------|---------------|------------|
| source | None | string | |
| destination | None | string | |

#### Return Value
ResultPayload object with connection creation status

#### Description
Creates a connection from the source parameter to the destination parameter. Both arguments should be in the format "node.param".

---

### exec_chain

```python
RetainedMode.exec_chain(*node_names)
```

Creates execution connections between a sequence of nodes.

#### Arguments

| Long Name | Short Name | Argument Type | Properties |
|-----------|------------|---------------|------------|
| *node_names | None | string(s) | |

#### Return Value
Dictionary with results of each connection attempt

#### Description
Creates exec_out -> exec_in connections between a sequence of nodes, effectively chaining them for execution in sequence.

---

### delete_connection

```python
RetainedMode.delete_connection(source_node_name, source_param_name, target_node_name, target_param_name)
```

Deletes a connection between parameters.

#### Arguments

| Long Name | Short Name | Argument Type | Properties |
|-----------|------------|---------------|------------|
| source_node_name | None | string | |
| source_param_name | None | string | |
| target_node_name | None | string | |
| target_param_name | None | string | |

#### Return Value
ResultPayload object with connection deletion status

#### Description
Removes the connection between the specified source and target parameters.

---

### get_connections_for_node

```python
RetainedMode.get_connections_for_node(node_name)
```

Lists all connections for a node.

#### Arguments

| Long Name | Short Name | Argument Type | Properties |
|-----------|------------|---------------|------------|
| node_name | None | string | |

#### Return Value
ResultPayload object containing connection information

#### Description
Returns all connections involving the specified node, both incoming and outgoing.

## Library Operations

### get_available_libraries

```python
RetainedMode.get_available_libraries()
```

Lists all available node libraries.

#### Arguments
None

#### Return Value
ResultPayload object containing a list of library names

#### Description
Returns all registered node libraries in the system.

---

### get_node_types_in_library

```python
RetainedMode.get_node_types_in_library(library_name)
```

Lists all node types in a library.

#### Arguments

| Long Name | Short Name | Argument Type | Properties |
|-----------|------------|---------------|------------|
| library_name | None | string | |

#### Return Value
ResultPayload object containing a list of node type names

#### Description
Returns all node types available in the specified library.

---

### get_node_metadata_from_library

```python
RetainedMode.get_node_metadata_from_library(library_name, node_type_name)
```

Gets metadata for a node type.

#### Arguments

| Long Name | Short Name | Argument Type | Properties |
|-----------|------------|---------------|------------|
| library_name | None | string | |
| node_type_name | None | string | |

#### Return Value
ResultPayload object containing node type metadata

#### Description
Returns the metadata for the specified node type in the given library.

## Config Operations

### get_config_value

```python
RetainedMode.get_config_value(category_and_key)
```

Gets a configuration value.

#### Arguments

| Long Name | Short Name | Argument Type | Properties |
|-----------|------------|---------------|------------|
| category_and_key | None | string | |

#### Return Value
ResultPayload object containing the configuration value

#### Description
Returns the value for the specified configuration key.

---

### set_config_value

```python
RetainedMode.set_config_value(category_and_key, value)
```

Sets a configuration value.

#### Arguments

| Long Name | Short Name | Argument Type | Properties |
|-----------|------------|---------------|------------|
| category_and_key | None | string | |
| value | None | any | |

#### Return Value
ResultPayload object with configuration update status

#### Description
Sets the value for the specified configuration key.

---

### get_config_category

```python
RetainedMode.get_config_category(category=None)
```

Gets all configuration values in a category.

#### Arguments

| Long Name | Short Name | Argument Type | Properties |
|-----------|------------|---------------|------------|
| category | None | string | |

Default: None

#### Return Value
ResultPayload object containing category configuration values

#### Description
Returns all configuration values in the specified category. If no category is provided, returns all configuration values.

---

### set_config_category

```python
RetainedMode.set_config_category(category=None, contents={})
```

Sets configuration values for a category.

#### Arguments

| Long Name | Short Name | Argument Type | Properties |
|-----------|------------|---------------|------------|
| category | None | string | |
| contents | None | dict | |

Default: None for category, empty dict for contents

#### Return Value
ResultPayload object with category configuration update status

#### Description
Sets all configuration values for the specified category with the provided contents.

## Utility Operations

### run_arbitrary_python

```python
RetainedMode.run_arbitrary_python(python_str)
```

Executes arbitrary Python code.

#### Arguments

| Long Name | Short Name | Argument Type | Properties |
|-----------|------------|---------------|------------|
| python_str | None | string | |

#### Return Value
ResultPayload object with execution status and results

#### Description
Executes the provided Python code string in the Griptape environment.

## Examples

### Creating a Flow and Nodes

```python
# Create a new flow
flow = RetainedMode.create_flow(flow_name="MyFlow")

# Create two nodes in the flow
node1 = RetainedMode.create_node(node_type="TextNode", node_name="TextInput", parent_flow_name="MyFlow")
node2 = RetainedMode.create_node(node_type="SummaryNode", node_name="TextSummary", parent_flow_name="MyFlow")
```

### Setting Parameter Values and Creating Connections

```python
# Set a parameter value
RetainedMode.set_value("TextInput.text", "This is a sample text to summarize.")

# Connect two nodes
RetainedMode.connect("TextInput.output", "TextSummary.input")

# Create an execution chain
RetainedMode.exec_chain("TextInput", "TextSummary")
```

### Running a Flow

```python
# Run the flow
RetainedMode.run_flow("MyFlow")

# Get the result
summary = RetainedMode.get_value("TextSummary.result")
print(summary)
```

### Modifying Parameters

```python
# Add a new parameter to a node
RetainedMode.add_param(
    node_name="TextSummary",
    parameter_name="max_length",
    default_value=100,
    tooltip="Maximum length of the summary in characters",
    type="int"
)

# Set the value of the new parameter
RetainedMode.set_value("TextSummary.max_length", 50)
```

### Listing and Querying

```python
# List all nodes in a flow
nodes = RetainedMode.get_nodes_in_flow("MyFlow")
print(nodes)

# List all parameters on a node
params = RetainedMode.list_params("TextSummary")
print(params)

# Check if a node exists
if RetainedMode.exists("TextInput"):
    print("TextInput node exists")
```