# InfoRetriever

## What is it?

The InfoRetriever uses Retrieval Augmented Generation or "RAG" capabilities to your workflows. Think of it as a smart researcher that can find and use relevant information to enhance AI responses.

## When would I use it?

Use this node when you want to:

- Ground AI responses in your own data sources
- Enable agents to access and reference specific information
- Improve response accuracy with relevant context
- Connect knowledge bases to your conversational agents

## How to use it

### Basic Setup

1. Add the InfoRetriever to your workflow
1. Connect its output to nodes that need RAG capabilities (like an Agent)

### Parameters

- **description**: A description of what information this tool provides (default is "Contains information")
- **off_prompt**: Whether to run RAG operations outside the main prompt (default is true)
- **rag_engine**: The engine used to retrieve information (required)

### Outputs

- **tool**: The configured RAG tool that other nodes can use
- **rules**: The ruleset used by the RAG tool

## Example

Imagine you want to create an agent that can answer questions using your company documentation:

1. Add an InfoRetriever to your workflow
1. Connect a vector store containing your documentation to the "rag_engine" input
1. Connect the "tool" output to an Agent's "tools" input
1. Now that agent can retrieve and reference specific information from your documentation when answering questions
