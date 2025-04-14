# Making Custom Scripts

## Getting Started with Custom Script Development

Creating your own custom scripts allows you to automate complex workflows, manipulate nodes programmatically, and extend Griptape Nodes functionality using Python.

## Understanding Retained Mode

Retained mode provides a comprehensive interface for interacting with Griptape Nodes programmatically:

- Create and manage flows and nodes
- Set and retrieve parameter values
- Establish connections between nodes
- Execute and control flow operations
- Access library information

## Custom Script Development Workflow

There are two primary ways to develop and use scripts in Griptape Nodes:

1. **Using the Script Editor** - Create scripts directly in the Griptape Nodes script editor for immediate execution

    - Access the script editor through the Griptape Nodes interface
    - Write your script using retained mode commands
    - Execute directly from the editor to modify or control your flows

1. **Importing External Scripts** - Import pre-written scripts into the script editor

    - Create reusable script modules in external files
    - Import them using Python's import system in the script editor
    - Execute the imported functionality from within the editor

The script editor currently serves as the primary entry point for all scripting operations in Griptape Nodes.

## Common Script Operations

The retained mode interface offers a comprehensive set of functions for manipulating and controlling Griptape Nodes:

- **Flow Management** - Create, delete, and query flows
- **Node Operations** - Create, delete, and manage nodes
- **Parameter Management** - List, get, and set parameter values
- **Connections** - Create and manage connections between nodes
- **Flow Execution** - Run, reset, and control flow execution

## Utility Script Types

You can create various types of utility scripts to enhance your workflow:

### Node Duplication

Create scripts that duplicate nodes with their properties and connections.

### Value Export and Import

Develop scripts to export node values and import them into other flows.

### Flow Creation

Build scripts that programmatically create entire flows with predefined nodes and connections.

## Advanced Scripting Techniques

### Working with Complex Parameters

Retained mode supports indexed access for working with complex data structures like lists and dictionaries.

### Bulk Operations

Scripts can automate repetitive tasks by performing operations on multiple nodes or connections in loops.

### Integration with External Libraries

Combine retained mode with other Python libraries like pandas, numpy, or requests to extend functionality.

## Best Practices for Custom Scripts

- Comment your code thoroughly for maintainability
- Use functions to organize complex operations
- Include error handling for robustness
- Use descriptive variable names
- Add logging for troubleshooting
- Consider creating a reusable script library
- Test scripts thoroughly before using in production

## Getting Help

If you encounter any issues while developing custom scripts, check out our [FAQ section](../faq.md) or reach out to our community for assistance through these channels:

- [Website](https://www.griptape.ai)
- [Discord Community](https://discord.gg/gnWRz88eym)
- [GitHub Repository](https://github.com/griptape-ai/griptape-nodes)
