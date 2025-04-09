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
2. Connect multiple text outputs from other nodes to this node's inputs
3. Optionally configure the separator string
4. Connect the output to nodes that require the combined text

### Parameters

**Inputs:**
- **inputs**: A list of text strings to be combined
- **merge_string**: The separator to place between text segments (defaults to "\n\n")

**Outputs:**
- **output**: The combined text result as a single string

## Example

A workflow to create a complete document from separate sections:

1. Add a MergeTexts node to your workflow
2. Connect outputs from three different text no