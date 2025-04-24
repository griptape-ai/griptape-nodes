# Calculator

## What is it?

The Calculator tool is a calculator. A calculator you give an agent. So the agent can do math.

## When would I use it?

Use this node when you want to:

- Enable agents to perform precise mathematical calculations
- Solve complex math problems within your workflow
- Process numerical data without writing custom calculation code

## How to use it

### Basic Setup

1. Add the Calculator to your workflow
1. Connect its output to nodes that need calculation capabilities (like an Agent)

### Parameters

- **off_prompt**: Whether to run calculations outside the main prompt (default is true)

### Outputs

- **tool**: The configured calculator tool that other nodes can use

## Example

Imagine you want to create an agent that can perform calculations:

1. Add a Calculator to your workflow
1. Connect the "tool" output to an Agent's "tools" input
1. Now that agent can perform calculations when needed in conversations
