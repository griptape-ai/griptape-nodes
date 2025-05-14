# SaveText

## What is it?

SaveText is a utility node that allows you to save text content to a file on your local system. This node provides a simple interface for writing text data to disk with a customizable output path.

## When would I use it?

Use this node when you want to:

- Save generated text content to a file
- Export results from your workflow to a text file
- Store conversation logs or outputs for later reference
- Create text files as part of your automated workflow
- Persist data between workflow runs

## How to use it

### Basic Setup

1. Add the SaveText node to your workflow
1. Connect a text source to the "text" input or enter text directly
1. Specify an output path or use the default
1. Run your workflow to save the text to the specified file

### Parameters

- **text**: The text content you want to save to a file (supports multiline text)
- **output_path**: The file path where the text will be saved (default is "griptape_output.txt")

### Outputs

- **output_path**: The path to the saved file (confirms successful save operation)

## Example

Imagine you want to save the output of an AI agent to a text file:

1. Add an Agent node to your workflow
1. Set up the agent with a prompt to generate some text
1. Add a SaveText node
1. Connect the Agent's "output" to the SaveText "text" input
1. Set the "output_path" to "my_agent_response.txt"
1. Run the workflow
1. The agent's response will be saved to "my_agent_response.txt" on your local system

## Important Notes

- The node will create the file if it doesn't exist, or overwrite it if it does
- The output_path parameter includes a save button in the UI for easy file selection
- You can use either relative or absolute paths for the output file
- The node will create any necessary parent directories if they don't exist
- The text is saved with UTF-8 encoding

## Common Issues

- **Permission Errors**: Ensure you have write permissions for the specified directory
- **Invalid Path**: Make sure the path is valid for your operating system
- **File Already Exists**: Be aware that existing files will be overwritten without confirmation
