# LoadText

## What is it?

The LoadText node is a utility node that reads text content from a file on your local system. It allows you to import existing text documents into your workflow for processing.

## When would I use it?

Use the LoadText node when:

- You need to import content from existing text files
- You want to process local documents with AI agents
- You're working with saved text data like logs, notes, or reports
- You need to feed external content into your workflow

## How to use it

### Basic Setup

1. Add a LoadText node to your workflow
1. Set the "path" parameter to the location of your text file
1. Connect the output to nodes that can process text content

### Parameters

- **path**: The file path to the text file you want to load (string)

### Outputs

- **output**: The content of the file as a text string
- **path**: The path to the loaded file (same as the input)

## Example

A workflow to analyze the content of a local text file:

1. Add a LoadText node to your workflow
1. Set the "path" parameter to something like "C:/Users/username/Documents/project_notes.txt"
1. Connect the "output" to an Agent node
