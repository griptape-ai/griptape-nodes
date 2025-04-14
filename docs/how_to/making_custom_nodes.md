# Making Custom Nodes

## Getting Started with Custom Node Development

Creating your own custom nodes allows you to extend functionality and tailor it to your specific needs.

## Using the Template Repository

The easiest way to get started is by using our official template repository:

[Griptape Nodes Library Template](https://github.com/griptape-ai/griptape-nodes-library-template/)

This template provides a structured foundation with all the necessary boilerplate code, testing frameworks, and documentation patterns to help you create production-ready node libraries.

[Go straight to the readme](https://github.com/griptape-ai/griptape-nodes-library-template/blob/main/README.md)

## Custom Node Development Workflow

1. **Use the template repository** - Create your own repository from the GitHub template
1. **Set up your environment** - Clone the repo to your Griptape Nodes workspace directory
1. **Configure your library** - Rename directories and update package information in `pyproject.toml`
1. **Create your nodes** - Define node classes (either ControlNode or DataNode) with appropriate parameters
1. **Implement your logic** - Code the required `process()` method and any additional functionality
1. **Configure library metadata** - Set up your library.json file with nodes and category information
1. **Register with the engine** - Add your library to Griptape Nodes through the settings interface
1. **Test and use** - Create flows using your custom nodes in the Griptape Nodes interface

## Best Practices for Custom Node Development

- Keep nodes focused on single responsibilities
- Follow Griptape's input/output patterns for consistency
- Add comprehensive error handling
- Include type hints and docstrings
- Write tests for both normal operation and edge cases
- Consider backward compatibility when updating nodes

## Example Use Cases

- Integration with company-specific APIs or services
- Custom data processing pipelines
- Domain-specific tools (financial calculations, scientific algorithms, etc.)
- Workflow automation specific to your organization
- Enhanced visualization or reporting capabilities

## Standard Library Reference

To better understand how to design your custom nodes, explore the patterns used in our standard library:

[Explore the standard node reference](../nodes/overview.md)

## Getting Help

If you encounter any issues while developing custom nodes, check out our [FAQ section](../faq.md) or reach out to our community for assistance through these channels:

- [Discord Community](https://discord.gg/gnWRz88eym)
- [Griptape Nodes GitHub Repository](https://github.com/griptape-ai/griptape-nodes)
