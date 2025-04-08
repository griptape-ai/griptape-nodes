# SaveText

## What is it?

The SaveText is a building block that lets you save text content to a file on your computer. Think of it as a way to keep and store the text your workflow creates.

## When would I use it?
Use this node when you want to:
- Save generated text to a file
- Export the results of your work
- Create text files from your workflow

## How to use it

### Basic Setup

1. Add the SaveText to your workspace
1. Connect it to your flow
1. Connect a source of text to its input

### Required Fields
- **text**: The text content you want to save (usually connected from another node)

### Optional Configuration
- **output_path**: The filename and location where you want to save the text (default is "griptape_output.txt")

### Outputs
- **output_path**: The path to the saved file (this can be used by other nodes if needed)

## Example
Imagine you have text from an agent that you want to save:

1. Connect the "output" from your agent node to the "text" input of the SaveText
1. Set "output_path" to "my_agent_response.txt"
1. Run your flow
1. The text will be saved to a file named "my_agent_response.txt"

## Important Notes
- If you don't specify an output path, the text will be saved to "griptape_output.txt" by default
- The node will create a new file or overwrite an existing file with the same name
- Make sure you have write permissions for the location where you're trying to save

## Common Issues
- **File Not Created**: Check if you have permission to write to the specified location
- **Empty File**: Make sure you've connected text to the "text" input
- **File Save Error**: Check if the path is valid and you have the necessary permissions