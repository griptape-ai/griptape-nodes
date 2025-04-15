# MergeTexts

## What is it?

The MergeTexts node is a utility node that combines multiple text strings into a single unified text output. It allows you to consolidate separate pieces of text with a configurable separator between them.

## When would I use it?

Use the MergeTexts node when:

- You need to combine text from multiple sources or nodes
- You want to join separate pieces of text with consistent formatting
- You're building a workflow that generates content from multiple components
- You need to create a comprehensive document from individual sections

## How to use it

### Basic Setup

1. Add a MergeTexts node to your workflow
1. Connect multiple text outputs from other nodes to this node's inputs
1. Optionally configure the separator string
1. Connect the output to nodes that require the combined text

### Parameters

- **inputs**: A list of text strings to be combined
- **merge_string**: The separator to place between text segments (defaults to "\\n\\n")

### Outputs

- **output**: The combined text result as a single string

## Example

A workflow to create a complete document from separate sections:

1. Add a MergeTexts node to your workflow
1. Connect outputs from three different text nodes (e.g., title, body, conclusion)
1. Set the merge_string parameter to "\\n\\n" for paragraph separation
1. The output will contain all text segments combined with the specified separator

## Important Notes

- Empty input strings are still included in the merge operation
- The separator is only added between inputs, not at the beginning or end

## Common Issues

- **Unexpected formatting**: Check that your merge_string contains appropriate whitespace
- **Missing content**: Verify all input connections are properly established
