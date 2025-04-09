# **Convert Agent to Tool Node Documentation**

### Overview

The `ConvertAgentToTool` class is a specialized node for converting an agent into a Griptape tool. This node provides a basic structure for initializing tools based on provided agents and can be extended to support various tool creation scenarios.

### Class Definition

```python
class ConvertAgentToTool(BaseTool):
    """A node for converting an agent into a Griptape tool."""
```

### Processing

The `process` method is called when the node is executed. It retrieves the values of the defined parameters and creates a new instance of the `StructureRunTool` class based on those values.

```python
def process(self) -> None:
    """Processes the node and sets the output parameter."""
    off_prompt = self.parameter_values.get("off_prompt", False)
    agent = self.parameter_values.get("agent", None)
    name = self.parameter_values.get("name", "Give the agent a name")
    description = self.parameter_values.get("description", "Describe what the agent should be used for")

    if agent:
        # Create a local structure function
        driver = LocalStructureRunDriver(create_structure=lambda: agent)

        # Create the tool
        tool = StructureRunTool(
            name=to_pascal_case(name),
            description=description,
            structure_run_driver=driver,
            off_prompt=off_prompt,
        )

        # Set the output
        self.parameter_output_values["tool"] = tool
    else:
        # Handle the case where no agent is provided
        self.parameter_output_values["tool"] = None
```

### Parameters

The `ConvertAgentToTool` class accepts the following parameters:

- **agent (Any)**: The agent to be converted into a tool. If not provided, the node will return `None`.
- **name (str)**: The name of the tool to be created. Defaults to "Give the agent a name" if not provided.
- **description (str)**: A description of the tool to be created. Defaults to "Describe what the agent should be used for" if not provided.

### Example Usage

To create a new instance of the `ConvertAgentToTool` class, you can use the following code:

```python
node = ConvertAgentToTool("My Tool")
node.parameter_values["agent"] = {"id": 1, "name": "Example Agent"}
node.process()
print(node.parameter_output_values["tool"])
```

This will create a new node with the name "My Tool" and process it to set the output parameter to the created tool instance.

### Notes

- The `LocalStructureRunDriver` class is not defined in this code snippet. It is assumed to be a separate class that provides the actual local structure function.
- The `to_pascal_case` function is used to convert the provided name into PascalCase format for the tool's name.
- The `parameter_values` and `parameter_output_values` attributes are not defined in this code snippet. They are assumed to be dictionaries that store the input and output parameters of the node, respectively.

### Best Practices

- When creating new nodes, ensure that you follow the same naming conventions and structure as existing nodes.
- Use meaningful parameter names and descriptions to make your nodes more user-friendly.
- Consider adding additional functionality or features to your nodes as needed.
