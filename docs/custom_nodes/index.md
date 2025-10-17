# Custom Nodes Authoring Guide

The **Custom Nodes** documentation explains how to build and maintain your own nodes for Griptape.

These nodes let you wrap common tools, scripts, and logic into reusable building blocks that can be shared across projects.

## Why build custom nodes

- Automate repetitive tasks
- Integrate existing tools into node graphs
- Create project-specific workflows without modifying the core framework
- Create new nodes _as you need them_ without waiting for anyone else to create them

This guide covers everything from writing a basic node to publishing a polished, well-tested library.

______________________________________________________________________

## Who this is for

- Node artists who would like to create a node to do something very specific
- Tech artists who need to build practical tools
- Pipeline TDs creating reusable node libraries
- Python developers reviewing or contributing to node code

Basic Python knowledge is assumed. Familiarity with Griptape helps but isn’t required to start.

______________________________________________________________________

## What you’ll learn

- How nodes work and where they fit in
- How to build and test a node
- How to create parameters and process them
- How to follow best practices for naming, structure, and versioning
- How to publish and share your node libraries

______________________________________________________________________

## Recommended Flow

If you’re new to authoring nodes, we suggest starting with the **101 Foundations** track and working your way up.
Each level builds on the previous one.

[101 – Foundations](101_foundations/index.md)

Get set up, understand the Sandbox, and create your first custom node.

[102 – Useful Nodes](102_useful_nodes/index.md)

Add parameters, handle inputs and outputs, and build your first practical node.

[201 – Professional Nodes](201_professional_nodes/index.md)

Learn testing, control flow, error handling, and when to use libraries.

[202 – Advanced Nodes](202_advanced_nodes/index.md)

Work with complex parameters, streaming, performance, and publishing.

You can jump directly to a higher level if you already have experience with node authoring, or follow the full flow from start to finish.

______________________________________________________________________

## Other sections

- [Concepts](concepts/nodes.md) — Nodes, ports, artifacts, and capabilities
- [How-to Guides](how-to/add-capabilities.md) — Task-based instructions
- [Testing](testing/overview.md) — How to test and set up CI
- [Best Practices](best-practices/naming.md) — Naming, structure, and versioning
- [Reference](reference/api-basics.md) — Templates, parameter types, and glossary
- [Examples](examples/text-utils.md) — Runnable sample nodes

______________________________________________________________________

## Prerequisites

- [Griptape Nodes](https://griptapenodes.com) installed
- Basic Python knowledge
- A code editor ([Visual Studio Code](https://code.visualstudio.com/), [Cursor](https://cursor.com/), etc.)
- Python 3.10+

For advanced topics (201+), you'll also need:

- [`uv`](https://github.com/astral-sh/uv) installed
- [Git](https://git-scm.com/) installed
- [GitHub](https://github.com/) account

______________________________________________________________________

!!! tip

    Start with something simple and build up.

    The goal is to understand the structure first, then layer on complexity as needed.
