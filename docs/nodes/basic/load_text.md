# LoadText

## What is it?

The LoadText is a building block that lets you read text from a file on your computer. Think of it as a way to bring existing text documents into your workflow.

## When would I use it?
Use this node when you want to:
- Use the contents of a text file in your workflow
- Process existing documents with your AI agents
- Work with saved text data, like logs or notes

## How to use it

### Basic Setup

1. Add the LoadText to your workspace
1. Connect it to your flow
1. Specify the path to the file you want to load

### Required Fields
- **path**: The location of the file you want to load (full path to the file)

### Outputs
- **output**: The content of the file as text
- **path**: The path to the loaded file (same as the input path)

## Example
Imagine you want to load the contents of a text file to analyze with an agent:

1. Add a LoadText to your workflow
1. Set the "path" to "C:/Documents/my_notes.txt" (or wherever your file is located)
1. Connect the "output" to another node (like an agent) that will process the text
1. When you run the flow, the contents of "my_notes.txt" will be loaded and made available

## Important Notes
- This node supports many file formats including: .txt, .md, .pdf, .json, .yaml, .csv, and more
- PDF files are handled differently than plain text files
- The full content of the file is loaded into memory, so be careful with very large files

## Common Issues
- **File Not Found**: Make sure the path is correct and the file exists
- **Permission Denied**: Check that you have permission to read the file
- **Unsupported Format**: Make sure your file has one of the supported extensions