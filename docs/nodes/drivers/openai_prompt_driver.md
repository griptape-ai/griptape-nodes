# OpenAiPrompt

## What is it?

The OpenAiPrompt node sets up a direct connection to OpenAI's chat models like GPT-4o.

## When would I use it?

Use this node when you want to:

- Use OpenAI's models in your workflow
- Customize how your agents interact with models like GPT-4o
- Control specific settings for OpenAI's responses

## How to use it

### Basic Setup

1. Add the OpenAiPrompt to your workflow
1. Connect its driver output to nodes that need to use OpenAI (like Agent)

### Parameters

- **model**: The OpenAI model to use (default is "gpt-4o")
- **response_format**: How you want responses formatted (options include "json_object")
- **seed**: A value to make responses more consistent between runs
- **stream**: Whether to receive responses as they're generated (true) or all at once (false)
- **temperature**: Controls randomness in responses (higher values = more creative, lower = more focused)
- **use_native_tools**: Whether to use OpenAI's built-in tools
- **max_tokens**: Maximum length of responses
- **max_attempts_on_fail**: How many times to retry if there's an error
- **min_p**: Controls diversity of outputs (converted to top_p internally)

### Outputs

- **driver**: The configured OpenAI driver that other nodes can use

## Example

Imagine you want to create an agent that uses GPT-4o with specific settings:

1. Add an OpenAiPrompt node to your workflow
1. Connect the "driver" output to an Agent's "prompt_driver" input

Things to try:

1. Set "model" to anything other than "gpt-4o"
1. Set "temperature" to 0.2 (for more focused, deterministic responses)
1. Set "max_tokens" to 2000 (for longer responses)

## Important Notes

- You need a valid OpenAI API key set up in your environment as `OPENAI_API_KEY`
- The default model is "gpt-4o"
- The min_p parameter is converted to top_p internally (top_p = 1 - min_p)
- Unlike some other drivers, OpenAI doesn't support the top_k parameter

## Common Issues

- **Missing API Key**: Make sure your OpenAI API key is properly set up
- **Connection Errors**: Check your internet connection and API key validity
- **Invalid Model**: Make sure you're using a model name that OpenAI supports
