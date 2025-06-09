# File Manager

## What is it?

The File Manager tool is a utility that can be given to an agent to help it perform file operations in your workspace directory.

## When would I use it?

Use this node when you want to:

- Enable agents to read and write files
- Manage files in your workspace directory
- Perform file operations like copying, moving, or deleting files

## How to use it

### Basic Setup

1. Add the File Manager tool to your workflow
1. Connect its output to nodes that need file operation capabilities (like an Agent)

### Outputs

- **tool**: The configured file manager tool that other nodes can use

## Example

Imagine you want to create an agent that can manage files:

1. Add a File Manager tool to your workflow
1. Connect the "tool" output to an Agent's "tools" input
1. Now that agent can perform file operations when needed in conversations

## Implementation Details

The File Manager tool is implemented using Griptape's `FileManagerTool` class with the `LocalFileManagerDriver`. The tool provides a simple interface for managing files in your workspace directory.

Note: Cloud storage functionality is currently disabled and will be available in a future update.
