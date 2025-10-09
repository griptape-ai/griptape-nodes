# Fetch MCP Server

The **Fetch MCP Server** provides web content fetching capabilities, allowing AI agents to retrieve and process content from web pages. It converts HTML to markdown for easier consumption and is perfect for research, content analysis, and web scraping tasks.

## What It Does

- **Fetches web content** from any publicly accessible URL
- **Converts HTML to markdown** for better readability
- **Handles various content types** including articles, documentation, and web pages
- **Provides clean, structured output** that AI agents can easily process

## Perfect For

- **Research tasks** - Gathering information from websites
- **Content analysis** - Processing articles and documentation
- **Web scraping** - Extracting data from web pages
- **News monitoring** - Keeping up with latest information
- **Documentation review** - Analyzing technical docs and guides

## Installation

### Prerequisites

- Node.js installed on your system
- Internet connection for fetching web content

### Setup Instructions

1. **Open Griptape Nodes** and go to **Settings** → **MCP Servers**

1. **Click + New MCP Server**

1. **Configure the server**:

    - **Server Name/ID**: `fetch`
    - **Connection Type**: `Local Process (stdio)`
    - **Configuration JSON**:

    ```json
    {
    "transport": "stdio",
    "command": "uvx",
    "args": ["mcp-server-fetch"],
    "env": {},
    "encoding": "utf-8",
    "encoding_error_handler": "strict"
    }
    ```

1. **Click Create Server**

## Usage Examples

### Basic Web Content Fetching

**Prompt**: `"Get the latest information about AI from https://www.anthropic.com/news"`

**Expected Output**: Clean markdown content from the Anthropic news page

### Research and Analysis

**Prompt**: `"Fetch the documentation from https://docs.python.org/3/tutorial/ and summarize the key concepts"`

**Expected Output**: Python tutorial content converted to markdown with AI-generated summary

### News Monitoring

**Prompt**: `"Check the latest news from https://techcrunch.com and tell me about the top 3 stories"`

**Expected Output**: Latest TechCrunch articles with AI analysis of the top stories

## Configuration Options

### Environment Variables

You can customize the fetch server behavior with environment variables:

```json
{
  "transport": "stdio",
  "command": "uvx",
  "args": ["mcp-server-fetch"],
  "env": {
    "FETCH_TIMEOUT": "30000",
    "FETCH_USER_AGENT": "MyApp/1.0"
  },
  "encoding": "utf-8",
  "encoding_error_handler": "strict"
}
```

### Available Environment Variables

| Variable           | Description                     | Default            |
| ------------------ | ------------------------------- | ------------------ |
| `FETCH_TIMEOUT`    | Request timeout in milliseconds | `30000`            |
| `FETCH_USER_AGENT` | User agent string for requests  | `mcp-server-fetch` |
| `FETCH_MAX_SIZE`   | Maximum response size in bytes  | `10485760` (10MB)  |

## Troubleshooting

### Common Issues

#### Server Not Responding

- Check your internet connection
- Verify the URL is accessible in a browser
- Try a different URL to test the server

#### Content Not Loading

- Some websites block automated requests
- Try adding a custom user agent
- Check if the site requires authentication

#### Timeout Errors

- Increase the `FETCH_TIMEOUT` value
- Try smaller, simpler pages first
- Check your network connection speed

#### Invalid URLs

- Ensure URLs include the protocol (http:// or https://)
- Check for typos in the URL
- Verify the website is accessible

The Fetch server is an excellent starting point for MCP workflows and provides a foundation for more complex web-based automation tasks!
