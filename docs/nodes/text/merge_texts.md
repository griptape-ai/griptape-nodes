# MergeTexts

!!! warning "Deprecation Notice"
    This node will be deprecated in a future version. We recommend using the **[JoinText](join_text.md)** node instead, which provides more flexibility with dynamic input handling and a cleaner interface.

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

- **input_1 through input_4**: Fixed number of text inputs to be combined
- **merge_string**: The separator to place between text segments (defaults to "\\n\\n" when trim_whitespace is False)
- **whitespace**: Boolean option to trim whitespace from each input and the final result

### Outputs

- **output**: The combined text result as a single string

## Example

A workflow to create a complete document from separate sections:

1. Add a MergeTexts node to your workflow
1. Connect outputs from three different text nodes (e.g., title, body, conclusion)
1. Set the merge_string parameter to "\\n\\n" for paragraph separation
1. The output will contain all text segments combined with the specified separator

## Important Notes

- When `whitespace` is enabled (trim mode), each input is trimmed of whitespace before joining
- When `whitespace` is enabled and the separator is empty, inputs are concatenated without any separator
- When `whitespace` is disabled, empty inputs are filtered out, and the separator defaults to "\\n\\n" if not specified
- The separator is only added between inputs, not at the beginning or end
- **Recommendation**: Consider using the **JoinText** node for more flexible input handling

## Common Issues

- **Unexpected formatting**: Check that your merge_string contains appropriate whitespace
- **Missing content**: Verify all input connections are properly established
