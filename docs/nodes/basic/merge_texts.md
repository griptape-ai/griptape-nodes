# MergeTexts

## What is it?

The MergeTexts is a building block that combines multiple pieces of text into a single text string. Think of it as taking several separate paragraphs and joining them together into one document.

## When would I use it?

Use this node when you want to:

- Combine text from multiple sources
- Join separate pieces of text with a consistent separator
- Create a single text output from multiple inputs

## How to use it

### Basic Setup

1. Add the MergeTexts to your workspace
1. Connect it to your flow
1. Connect multiple text inputs to it

### Required Fields

- **inputs**: A list of text strings you want to combine

### Optional Configuration

- **merge_string**: The separator to use between each piece of text (default is a double line break: "\\n\\n")

### Outputs

- **output**: The combined text result

## Example

Imagine you have three pieces of text:

- "Hello, my name is Alice."
- "I live in New York."
- "I work as an engineer."

Using the default separator ("\\n\\n"), the merged result would be:

```
Hello, my name is Alice.

I live in New York.

I work as an engineer.
```

## Important Notes

- You can customize how texts are joined by changing the merge_string
- Common merge_string options include:
  - `\n` (single line break)
  - `\n\n` (paragraph break - the default)
  - ` ` (single space)
  - `, ` (comma and space)
- You can use `\\n` in the merge_string to represent a line break
- None values in the input list are ignored

## Common Issues

- **Unexpected Formatting**: Check your merge_string if the spacing between texts doesn't look right
- **Missing Text**: Make sure all your text inputs are properly connected
