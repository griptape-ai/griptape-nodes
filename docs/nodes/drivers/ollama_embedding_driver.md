# OllamaEmbeddingDriver

## What is it?

The OllamaEmbeddingDriver is a building block that sets up a connection to Ollama's embedding service. Think of it as configuring a tool that can convert text into special number patterns (embeddings) that help AI understand relationships between different pieces of text.

## When would I use it?

Use this node when you want to:

- Create embeddings using locally-hosted Ollama models
- Prepare text for similarity searches or semantic matching
- Work with vector databases or semantic search in your workflow

## How to use it

### Basic Setup

1. Add the OllamaEmbeddingDriver to your workspace
2. Connect it to your flow
3. Connect its output to nodes that need to use text embeddings

### Parameters

- **base_url**: The URL where your Ollama server is running (default is "http://127.0.0.1")
- **port**: The port your Ollama server is using (default is "11434")
- **embedding_model**: The model to use for creating embeddings (default is "all-minilm")

### Outputs

- **driver**: The configured Ollama embedding driver that other nodes can use

## Example

Imagine you want to create embeddings to use for finding similar text:

1. Add an OllamaEmbeddingDriver to your workflow
1. Set "base_url" to match your Ollama server (usually "http://127.0.0.1")
1. Set "embedding_model" to "all-minilm" or another embedding model you've pulled into Ollama
1. Connect the "driver" output to a node that processes embeddings
1. When you run the flow, text will be converted to embeddings that can be used for semantic matching

## Important Notes

- You need Ollama running locally (or accessible at the specified URL)
- The default model is "all-minilm" which is a good general-purpose embedding model
- Make sure you've pulled the appropriate embedding model into Ollama before using it

## Common Issues

- **Connection Error**: Make sure Ollama is running and accessible at the specified URL and port
- **Missing Model**: If the embedding model isn't available in Ollama, you'll need to pull it first
- **Wrong URL/Port**: Double-check that the base_url and port match your Ollama setup
