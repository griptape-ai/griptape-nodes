# Search Web

## What is it?

The Search Web tool is a utility that allows you to search the web and retrieve text content from search results.

## When would I use it?

Use this node when you want to:

- Search the web for specific information
- Retrieve text content from search results
- Gather information from multiple web sources
- Research topics online

## How to use it

### Basic Setup

1. Add the Search Web tool to your workflow
1. Connect its output to nodes that need web search results

### Parameters

- **prompt**: The search query to use
- **summarize**: Whether or not you want an LLM to summarize the text
- **search_engine**: The search engine to use. Note: some engines require an API key.

### Outputs

- **output**: The text content retrieved from the search results

## Example

Imagine you want to search for information about a specific topic:

1. Add a Search Web tool to your workflow
1. Set the search query
1. Connect the "output to another node that needs the search results
1. The tool will return the text content from the search results

## Implementation Details

The Search Web tool uses web search capabilities to find relevant information and extracts text content from the search results. It's designed to help you gather information from the web in a structured way.
