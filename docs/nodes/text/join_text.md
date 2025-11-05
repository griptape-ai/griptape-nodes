# JoinText

## What is it?

The JoinText node is a utility node that combines multiple text strings into a single unified text output. It provides flexible input handling through a dynamic list parameter, allowing you to join any number of text inputs with a configurable separator.

## When would I use it?

Use the JoinText node when:

- You need to combine text from multiple sources or nodes
- You want to join separate pieces of text with consistent formatting
- You're building a workflow that generates content from multiple components
- You need to create a comprehensive document from individual sections
- You need dynamic input handling (variable number of inputs)

## How to use it

### Basic Setup

1. Add a JoinText node to your workflow
1. Connect multiple text outputs from other nodes to the `text` parameter (a list parameter)
1. Optionally configure the `join_string` separator
1. Connect the output to nodes that require the combined text

### Parameters

- **text**: A dynamic list parameter that accepts any number of text strings to be joined

- **join_string**: The separator to place between text segments (defaults to "\\n\\n" if not specified)

    - Can be an empty string to concatenate without any separator
    - Supports escaped sequences like "\\n" for newlines

### Outputs

- **output**: The combined text result as a single string (with leading/trailing whitespace stripped)

## Example

A workflow to create a complete document from separate sections:

1. Add a JoinText node to your workflow
1. Connect outputs from multiple text nodes (e.g., title, body, conclusion) to the `text` parameter
1. Set the `join_string` parameter to "\\n\\n" for paragraph separation
1. The output will contain all text segments combined with the specified separator

## Important Notes

- The `text` parameter is a dynamic list, so you can add or remove inputs as needed
- Empty strings in the input list are preserved and will appear in the output
- The separator defaults to "\\n\\n" (double newline) if not specified or set to None
- The final output is stripped of leading and trailing whitespace
- If the separator is an empty string, inputs are concatenated directly without any separator

## Common Issues

- **Unexpected formatting**: Check that your `join_string` contains appropriate whitespace or separator characters
- **Missing content**: Verify all input connections are properly established in the `text` parameter list
- **Empty separator behavior**: An empty string separator will concatenate inputs directly without any separator between them
