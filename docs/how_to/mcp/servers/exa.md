# Exa MCP Server

The **Exa MCP Server** provides powerful web search and research capabilities through Exa AI's advanced search engine. It offers both local and remote deployment options, with specialized tools for code search, web research, and content extraction.

## What It Does

- **Advanced web search** - Real-time web searches with optimized results
- **Code search** - Find relevant code snippets and documentation from GitHub repos
- **Content extraction** - Extract content from specific URLs
- **Company research** - Comprehensive business intelligence gathering
- **LinkedIn search** - Search for companies and people on LinkedIn
- **Deep research** - AI-powered research reports on complex topics

## Perfect For

- **Code development** - Find implementation examples and API documentation
- **Research projects** - Gather information from multiple sources
- **Business intelligence** - Research companies and market trends
- **Content analysis** - Extract and analyze web content
- **Academic research** - Deep dive into complex topics

## Installation

The easiest way to use Exa is through their hosted MCP server:

1. **Open Griptape Nodes** and go to **Settings** → **MCP Servers**
1. **Click + New MCP Server**
1. **Configure the server**:

    - **Server Name/ID**: `exa`
    - **Connection Type**: `Streamable HTTP`
    - **Configuration JSON**:

    ```json
    {
    "transport": "streamable_http",
    "url": "https://mcp.exa.ai/mcp"
    }
    ```

1. **Click Create Server**

## Available Tools

### 🔥 Featured: Code Search
- **`get_code_context_exa`** - Search billions of GitHub repos, docs, and Stack Overflow for relevant code examples
- **Perfect for developers** - Find up-to-date implementation examples and API usage patterns

### 🌐 Web Search & Research
- **`web_search_exa`** - Real-time web searches with optimized results
- **`crawling`** - Extract content from specific URLs
- **`company_research`** - Comprehensive company information gathering
- **`linkedin_search`** - Search LinkedIn for companies and people

### 🧠 Advanced Research
- **`deep_researcher_start`** - Start AI-powered research on complex topics
- **`deep_researcher_check`** - Get comprehensive research reports

## Usage Examples

### Code Development

**Prompt**: `"Find examples of using the Vercel AI SDK to call GPT-4 with proper error handling"`

**Expected Output**: Relevant code snippets from GitHub repositories and documentation

### Web Research

**Prompt**: `"Research the latest developments in AI safety and summarize the key findings"`

**Expected Output**: Comprehensive research report with sources and analysis

### Company Research

**Prompt**: `"Find information about Anthropic's latest funding round and business model"`

**Expected Output**: Detailed company information from multiple sources

### Content Extraction

**Prompt**: `"Extract the main points from this article: https://example.com/article"`

**Expected Output**: Clean, structured content from the specified URL

## Configuration Options

### Tool Selection

You can enable specific tools by adding them to your configuration:

```json
{
  "transport": "streamable_http",
  "url": "https://mcp.exa.ai/mcp",
  "enabled_tools": ["get_code_context_exa", "web_search_exa"]
}
```

### Available Tool Combinations

#### For Developers
```json
"enabled_tools": ["get_code_context_exa", "web_search_exa"]
```

#### For Researchers
```json
"enabled_tools": ["web_search_exa", "deep_researcher_start", "deep_researcher_check"]
```

#### For Business Intelligence
```json
"enabled_tools": ["company_research", "linkedin_search", "web_search_exa"]
```

#### All Tools
```json
"enabled_tools": ["get_code_context_exa", "web_search_exa", "company_research", "crawling", "linkedin_search", "deep_researcher_start", "deep_researcher_check"]
```

## Troubleshooting

### Common Issues

#### Connection Issues
- Test the remote server URL: `https://mcp.exa.ai/mcp`
- Check your internet connection
- Verify firewall settings allow HTTPS connections

#### Tool Not Available
- Ensure the tool is enabled in your configuration
- Check the tool name spelling
- Verify the tool is available in the current Exa service

### Debug Tips

1. **Test with simple queries** first
2. **Check the Exa dashboard** for usage and errors
3. **Use the remote server** for easier troubleshooting
4. **Start with basic tools** before using advanced features

The Exa MCP server is perfect for developers and researchers who need powerful search capabilities with minimal setup!
