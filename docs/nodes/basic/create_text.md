# CreateText

## What is it?

The CreateText is a simple building block that creates a piece of text (a string) that you can use in your workflow. Think of it as a notepad where you can write text to use elsewhere.

## When would I use it?

Use this node when you want to:

- Enter a fixed piece of text into your workflow
- Create text that doesn't change (like a template or message)
- Provide text input for other nodes

## How to use it

### Basic Setup

1. Add the CreateText to your workspace
1. Connect it to your flow

### Fields

- **text**: The text content you want to create (defaults to "<Empty>" if not set)

### Outputs

- **text**: The text string that can be used by other nodes in your flow

## Example

Imagine you want to provide a standard greeting for an agent to use:

1. Add a CreateText to your workflow
1. Set the "text" value to "Hello! How can I help you today?"
1. Connect the "text" output to another node that needs this greeting text

## Important Notes

- The default value is "<Empty>" if you don't set anything
- You can edit the text directly in the node properties
- This node just passes the text value through - it doesn't process or change the text

## Common Issues

- **Text Not Updating**: Make sure you've saved changes to the text property
- **Formatting Issues**: The text will be exactly as you enter it, including spaces and line breaks
