# OllamaPrompt

## What is it?

The OllamaPrompt node sets up a connection to locally-run AI models through Ollama. These AI models run on your own computer, locally, instead of in the cloud.

## When would I use it?

Use this node when you want to:

- Use locally-hosted AI models in your workflow
- Work with your data privately without sending it to external services
- Use open-source models available through Ollama

## How to use it

### Basic Setup

1. Add the OllamaPrompt node to your workflow
1. Connect its driver output to nodes that can use LLMs (like an Agent)

### Parameters

- **model**: The Ollama model to use (default is "llama3.2")
- **temperature**: Controls randomness in responses (higher values = more creative, lower = more focused)
- **max_attempts_on_fail**: How many times to retry if there's an error
- **use_native_tools**: Whether to use any built-in tools
- **max_tokens**: Maximum length of responses
- **min_p**: Controls diversity of outputs
- **top_k**: Controls focus on most likely tokens

### Outputs

- **driver**: The configured Ollama driver that other nodes can use

## Example

Imagine you want to create an agent that uses a local Llama model:

1. Add an OllamaPrompt node to your workflow
1. Set "model" to "llama3.2" (or any other model you've pulled into Ollama)
1. Connect the "driver" output to an Agent's "prompt_driver" input

Try:

1. Set "temperature" to 0.8 (for more creative responses)

## Important Notes

- You need to have [Ollama](https://ollama.com/) installed and running on your computer
- The default connection is to http://127.0.0.1:11434
- The default model is "llama3.2"
- Make sure you've pulled the model you want to use in Ollama before using it in your workflow

## Common Issues

- **Connection Error**: Make sure Ollama is running on your computer
- **Missing Model**: If the model isn't available in Ollama, you'll need to pull it first
- **Resource Limitations**: Local models may be slower or less capable than cloud models, depending on your hardware.
- **Tool Limitations**: Local models may not be able to use tools the way cloud models do.