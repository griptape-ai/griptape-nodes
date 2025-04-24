# CoherePrompt

## What is it?

The CoherePrompt node sets up a connection to Cohere's AI models.

## When would I use it?

Use this node when you want to:

- Use Cohere's AI models in your workflow
- Take advantage of Cohere's specific capabilities

## How to use it

### Basic Setup

1. Add the CoherePrompt node to your workflow
1. Connect its output to nodes that can use prompt drivers (like Agent)

### Parameters

- **model**: The Cohere model to use (default is "command-r-plus")
- **max_attempts_on_fail**: How many times to retry if there's an error
- **use_native_tools**: Whether to use Cohere's built-in tools
- **max_tokens**: Maximum length of responses
- **min_p**: Controls diversity of outputs (similar to temperature)
- **top_k**: Controls focus on most likely tokens

### Outputs

- **driver**: The configured Cohere driver that other nodes can use

## Example

If you want to create an agent that uses Cohere:

1. Add a CoherePrompt node to your workflow
1. Connect the "driver" output to an Agent's "prompt_driver" input

Try:

1. Set "model" to something besides the default
1. Set "max_tokens" to 1000 (for moderate length responses)

## Important Notes

- You need a valid Cohere API key set up in your environment as `COHERE_API_KEY`
- The default model is "command-r-plus"
- The node checks if your API key is valid during setup

## Common Issues

- **Missing API Key**: Make sure your Cohere API key is properly set up
- **Connection Errors**: Check your internet connection and API key validity
