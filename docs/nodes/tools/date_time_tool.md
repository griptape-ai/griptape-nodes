# DateTimeTool

## What is it?

The DateTimeTool is a building block that provides date and time capabilities to your workflows. Think of it as a digital calendar and clock that your agents can use to format, manipulate, and work with dates and times.

## When would I use it?

Use this node when you want to:

- Enable agents to access current date and time information
- Format dates in different styles for various use cases
- Perform date calculations like finding differences between dates
- Convert between time zones and date formats

## How to use it

### Basic Setup

1. Add the DateTimeTool to your workspace
1. Connect it to your flow
1. Connect its output to nodes that need date/time capabilities (like an Agent)

### Parameters

- **off_prompt**: Whether to run date/time operations outside the main prompt (default is true)

### Outputs

- **tool**: The configured date/time tool that other nodes can use

## Example

Imagine you want to create an agent that can work with dates and times:

1. Add a DateTimeTool to your workflow
1. Connect the "tool" output to an Agent's "tools" input
1. Now that agent can perform operations like getting the current date, formatting dates, or calculating date differences
