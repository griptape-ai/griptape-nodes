# DateTime

## What is it?

The DateTime tool provides date and time capabilities to your workflows. It can figure out and write dates and times in all kinds of formats, calculate dates by adding and subtracting stretches of time, and even provide countdowns and days-since type things.

## When would I use it?

Use this node when you want to:

- Enable agents to access current date and time information
- Format dates in different styles for various use cases
- Perform date calculations like finding differences between dates
- Convert between time zones and date formats

## How to use it

### Basic Setup

1. Add the DateTime node to your workflow
1. Connect its output to nodes that can make use of date/time capabilities (like an Agent)

### Parameters

- **off_prompt**: Whether to run date/time operations outside the main prompt (default is true)

### Outputs

- **tool**: The configured date/time tool that other nodes can use

## Example

Imagine you want to create an agent that can work with dates and times:

1. Add a DateTime node to your workflow
1. Connect the "tool" output to an Agent's "tools" input
1. Now that agent can perform operations like getting the current date, formatting dates, or calculating date differences
