# Date Time

## What is it?

The Date Time tool is a utility that can be given to an agent to help it perform date and time operations.

## When would I use it?

Use this node when you want to:

- Enable agents to work with dates and times
- Perform date/time calculations and manipulations
- Get current time information
- Format dates and times in different ways

## How to use it

### Basic Setup

1. Add the Date Time tool to your workflow
1. Connect its output to nodes that need date/time capabilities (like an Agent)

### Outputs

- **tool**: The configured date time tool that other nodes can use

## Example

Imagine you want to create an agent that can work with dates and times:

1. Add a Date Time tool to your workflow
1. Connect the "tool" output to an Agent's "tools" input
1. Now that agent can perform date and time operations when needed in conversations

## Implementation Details

The Date Time tool is implemented using Griptape's `DateTimeTool` class and provides a comprehensive interface for handling date and time operations. The tool is designed to be used by agents to manage temporal data and perform time-based calculations.
