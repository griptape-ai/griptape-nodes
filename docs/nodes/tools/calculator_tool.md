# CalculatorTool

## What is it?

The CalculatorTool is a building block that provides calculation capabilities to your workflows. Think of it as a powerful calculator that your agents can use to perform mathematical operations and calculations.

## When would I use it?

Use this node when you want to:

- Enable agents to perform precise mathematical calculations
- Solve complex math problems within your workflow
- Process numerical data without writing custom calculation code

## How to use it

### Basic Setup

1. Add the CalculatorTool to your workspace
2. Connect it to your flow
3. Connect its output to nodes that need calculation capabilities (like an Agent)

### Parameters

- **off_prompt**: Whether to run calculations outside the main prompt (default is true)

### Outputs

- **tool**: The configured calculator tool that other nodes can use

## Example

Imagine you want to create an agent that can perform calculations:

1. Add a CalculatorTool to your workflow
2. Connect the "tool" output to an Agent's "tools" input
3. Now that agent can perform calculations when needed in conversations
