# Filesystem MCP Server

The **[Filesystem MCP Server](https://github.com/modelcontextprotocol/servers/blob/main/src/filesystem/README.md)** enables AI agents to perform file and directory operations on your local machine. It provides secure, controlled access to specific directories for file management, content organization, and data processing tasks.

## What It Does

- **File operations** - Read, write, create, and delete files
- **Directory management** - Create, list, and navigate directories
- **File search** - Find files by name, pattern, or content
- **Content processing** - Organize and manage your local files
- **Secure access** - Only accesses directories you explicitly allow

## Perfect For

- **File organization** - Automatically sort and organize your files
- **Content management** - Process and manage documents and media
- **Data processing** - Work with local data files and datasets
- **Backup operations** - Create and manage file backups
- **Document analysis** - Read and analyze local documents

## Installation

### Prerequisites
- Node.js installed on your system
- Access to the directories you want to manage

### Setup Instructions

1. **Open Griptape Nodes** and go to **Settings** → **MCP Servers**
1. **Click + New MCP Server**
1. **Configure the server**:

    - **Server Name/ID**: `filesystem`
    - **Connection Type**: `Local Process (stdio)`
    - **Configuration JSON**:

    ```json
    {
    "transport": "stdio",
    "command": "npx",
    "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path/to/allowed/directory"],
    "env": {},
    "encoding": "utf-8",
    "encoding_error_handler": "strict"
    }
    ```

1. **Click Create Server**

### Multiple Directory Access
To allow access to multiple directories, add them as separate arguments:

```json
{
  "transport": "stdio",
  "command": "npx",
  "args": [
    "-y",
    "@modelcontextprotocol/server-filesystem",
    "/Users/username/Desktop",
    "/Users/username/Downloads",
    "/Users/username/Documents"
  ],
  "env": {},
  "encoding": "utf-8",
  "encoding_error_handler": "strict"
}
```

## Available Tools

The Filesystem MCP server provides these key capabilities:

- **read_file** - Read file contents
- **write_file** - Write content to files
- **list_directory** - List directory contents
- **create_directory** - Create new directories
- **search_files** - Find files by name or pattern
- **move_file** - Move or rename files
- **delete_file** - Remove files

## Security Features

- **Directory restrictions** - Can only access specified directories
- **Permission respect** - Follows your system's file permissions
- **Sandboxed operations** - Cannot access files outside allowed paths
- **Controlled access** - You explicitly define which directories are accessible

## Resources

- [Filesystem MCP Server](https://github.com/modelcontextprotocol/servers/blob/main/src/filesystem/README.md) - Official repository and documentation
- [Node.js File System API](https://nodejs.org/api/fs.html) - Reference for file operations

## Next Steps

- **[Local Models with Agents](../advanced_local_models.md)** - Keep file processing private
- **[Time MCP Server](./time.md)** - Add date/time operations to your workflows
- **[MCPTask with Agents](../mcp_task_agents.md)** - Advanced agent integration patterns

The Filesystem MCP server is essential for any workflow that needs to interact with your local files!