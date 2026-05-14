# Developing Nodes

This section provides comprehensive documentation for developers building custom nodes for Griptape Nodes.

!!! tip "For AI Assistants & Coding Agents"

    All documentation in this section is available as post-processed markdown for AI coding assistants. The site exposes a full machine-readable surface; see [For Agents](../for_agents.md) for the index.

    - **Getting Started**: [https://docs.griptapenodes.com/developing_nodes/getting_started/index.md](https://docs.griptapenodes.com/developing_nodes/getting_started/index.md)
    - **Comprehensive Guide**: [https://docs.griptapenodes.com/developing_nodes/comprehensive_guide/index.md](https://docs.griptapenodes.com/developing_nodes/comprehensive_guide/index.md)
    - **Example Code**: [View Python Example](https://raw.githubusercontent.com/griptape-ai/griptape-nodes/main/docs/developing_nodes/example_control_node.py)

    **Usage:** Point your AI assistant to these URLs with instructions like:
    `"Read this node development guide: [URL] and help me build a custom node"`

## Getting Started

If you're new to developing nodes, start with the [Getting Started Guide](getting_started.md). This guide provides a beginner-friendly introduction to the node development ecosystem and walks you through building your first node.

## Comprehensive Reference

For detailed technical information, see the [Comprehensive Node Development Guide](comprehensive_guide.md). This exhaustive reference covers:

- Node base classes (`DataNode`, `ControlNode`, `StartNode`, `EndNode`, etc.)
- Parameters, traits, containers, and lifecycle callbacks
- Async patterns (`AsyncResult`)
- Advanced UI/UX and error-handling guidance
- Creating and distributing node libraries
- Custom widget components
- Production best practices

## Practical Examples

- [Example Control Node](example_control_node.py) - A complete working example demonstrating best practices for building control nodes

## Quick Links

- **Quick Start**: [Making Custom Nodes](../how_to/making_custom_nodes.md) - Template for rapid node creation
- **Custom Scripts**: [Making Custom Scripts](../how_to/making_custom_scripts.md) - Build custom node execution scripts

## Documentation Structure

1. **[Getting Started](getting_started.md)** - Your first node and essential concepts
1. **[Comprehensive Guide](comprehensive_guide.md)** - Complete technical reference
1. **[Example Code](example_control_node.py)** - Practical implementation patterns
