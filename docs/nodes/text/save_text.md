# SaveText

## What is it?

The SaveText node is a utility node that writes text content to a file on your local system. It allows you to persist text output from your workflow as a file on disk.

## When would I use it?

Use the SaveText node when:

- You need to save generated text content to a file
- You want to export workflow results for later use
- You're creating reports, documents, or data files from your workflow
- You need to persist the output of AI agents or other text processing

## How to use it

### Basic Setup

1. Add a SaveText node to your workflow
2. Connect a text output from another node to this node's text input
3. Optionally specify the output file path
4. Run your workflow to save the text to disk

### Parameters

**Inputs:**
- **text**: The text content to save (string)
- **output_path**: The file path where the text should be saved (defaults to "griptape_output.txt")

**Outputs:**
- **output_path**: The path of the file where the text was saved

## Example

A workflow to generate and save AI-created content:

1. Add a SaveText node to your workflow
2. Connect an Agent node's response output to the "text" input
3. Set "output_path" to "C:/Users/username/Documents/agent_response.txt"
4. When the workflow runs, the agent's response will be saved to the specified file

## Important Notes

- If no output path is specified, text is saved to "griptape_output.txt" in the current directory
- The node will create a new file or overwrite an existing file with the same name
- Directories in the path must already exist - the node won't create new directories
- Relative paths are resolved relative to the current working directory

## Common Issues

- **Permission Error**: Ensure you have write permissions for the specified location
- **Directory Not Found**: Verify that all directories in the path exist
- **No Content Saved**: Check that the text input is properly connected and contains content
- **Path Format**: On Windows, use either forward slashes (/) or escaped backslashes (\\\\)