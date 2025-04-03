# DuckDuckGoWebSearchDriverNode

## What is it?

The DuckDuckGoWebSearchDriverNode is a building block that sets up a connection to the DuckDuckGo search engine. Think of it as giving your workflow the ability to search the internet for information.

## When would I use it?

Use this node when you want to:

- Allow your workflow to look up information on the internet
- Get real-time data that might not be in your AI model's knowledge
- Research topics or find current information

## How to use it

### Basic Setup

1. Add the DuckDuckGoWebSearchDriverNode to your workspace
1. Connect it to your flow
1. Connect its output to nodes that need web search capabilities

### Required Fields

None - this node works without additional configuration

### Outputs

- **driver**: The configured DuckDuckGo web search driver that other nodes can use

## Example

Imagine you want to create an agent that can search the web for current information:

1. Add a DuckDuckGoWebSearchDriverNode to your workflow
1. Connect the "driver" output to a node that uses web search tools
1. When you run the flow, your agent will be able to search the internet using DuckDuckGo

## Important Notes

- No API key is required as DuckDuckGo's search is freely available
- The search results will reflect what's publicly available on the internet
- This node only configures the search capability - you'll need to connect it to tools or agents that actually perform searches

## Common Issues

- **No Search Results**: The search might not find relevant information for very specific or unusual queries
- **Connection Errors**: Requires an internet connection to function
- **Rate Limiting**: If too many searches are performed rapidly, DuckDuckGo might temporarily limit access
