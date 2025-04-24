# Note

## What is it?

The Note node allows you to create descriptive notes throughout your workflow. They are not really operative, but more meant for display and documentation within a flow.

## When would I use it?

Use the Note node when:

- You need to describe what a section of your workflow does.
- You want to give yourself a hint as to how to use a particular node.
- You want to instruct someone else what to do with your workflow.

## How to use it

### Basic Setup

1. Add a Note node to your workflow
1. Set the "note" parameter with your desired multiline content

### Parameters

- **note**: The text content (string, defaults to empty string)

## Example

A workflow to create a note for how to use `prompt_context` on an Agent.

1. Add a Note node to your workflow

1. Move the Note near your Agent node

1. Enter the following text

    ```
    To use the prompt_context, create a new KeyValuePair node.
    Give it something like a key of "style" and a value of "haiku"
    Then, connect the dictionary output to the prompt_context on your Agent.
    In the Agent prompt, use the {{ }} character to specify where you want to
    replace "style" with "haiku". Example:

    Tell me about skateboards in the style of a {{style}}
    ```

1. Position the Note where it is easy to read and helps you understand your workflow

## Important Notes

- Line breaks are preserved
- The node supports any valid string content
- Empty strings are valid
- There is no character limit

## Common Issues

- There is no control on the font size yet
- There is no control for the color of the node yet
