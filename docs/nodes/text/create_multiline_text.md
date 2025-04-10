# CreateMultilineText

## What is it?

The CreateMultilineText node is a utility node that creates and outputs a multiline text string. It allows you to define text content with multiple lines that can be passed to other nodes in your workflow.

## When would I use it?

Use the CreateMultilineText node when:

- You need to create text content with multiple lines of text
- You want to prepare text input for other nodes in your workflow
- You need to define prompts, instructions, or other multi-paragraph content
- You're building workflows that require structured text input

## How to use it

### Basic Setup

1. Add a CreateMultilineText node to your workflow
2. Set the "text" parameter with your desired multiline content
3. Connect the output to nodes that accept text input

### Parameters

- **text**: The multiline text content (string, defaults to empty string)

### Outputs
- **text**: The multiline text content as a string

## Example

A workflow to create a prompt for an AI assistant:

1. Add a CreateMultilineText node to your workflow
2. Set the "text" parameter to:
```
You are a helpful tour guide assistant.
Please provide information about the following location:
- History of the place
- Main attractions
- Best time to visit
- Local cuisine
```
3. Connect the output to an Agent node's prompt parameter

## Important Notes

- Line breaks are preserved in the output
- The node supports any valid string content
- Empty strings are valid input and will produce an empty string output
- There is no character limit, but extremely large text blocks may impact performance

## Common Issues

- Text formatting issues when copying from different sources (check for unexpected characters)
- Line breaks might render differently in different env