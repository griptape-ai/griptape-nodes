# Web Search

## What is it?

The Web Search tool is a utility that can be given to an agent to help it search the web. It supports multiple search engines including DuckDuckGo, Google, and Exa.

## When would I use it?

Use this node when you want to:

- Enable agents to search the web for information
- Access real-time web data
- Perform research tasks
- Get up-to-date information from the internet

## How to use it

### Basic Setup

1. Add the Web Search tool to your workflow
1. Connect its output to nodes that need web search capabilities (like an Agent)

### Parameters

- **search_engine**: The search engine to use (default is "DuckDuckGo")

    - Options:

        - DuckDuckGo: Free, no API key required
        - Google: Requires Google API key and Search ID
        - Exa: Requires Exa API key

### Outputs

- **tool**: The configured web search tool that other nodes can use

## Example

Imagine you want to create an agent that can search the web:

1. Add a Web Search tool to your workflow
1. Connect the "tool" output to an Agent's "tools" input
1. Now that agent can perform web searches when needed in conversations

## Implementation Details

The Web Search tool is implemented using Griptape's `WebSearchTool` class and supports multiple search engine drivers:

- `DuckDuckGoWebSearchDriver`: Free, no API key required
- `GoogleWebSearchDriver`: Requires Google API key and Search ID
- `ExaWebSearchDriver`: Requires Exa API key

When using Google or Exa search engines, you'll need to set up the appropriate API keys in the configuration. The tool will automatically handle authentication and search operations with the selected engine.
