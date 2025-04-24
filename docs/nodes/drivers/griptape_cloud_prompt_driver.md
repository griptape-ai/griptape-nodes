# GriptapeCloudPrompt

## What is it?

The GriptapeCloudPrompt node sets up a connection to Griptape Cloud's AI services.

## When would I use it?

Use this node when you want to:

- Use various AI models through the Griptape Cloud service (you won't have to go register with OpenAI and get an api key)
- Customize which AI model for anything that takes a prompt driver

## How to use it

### Basic Setup

1. Add a GriptapeCloudPrompt node to your workflow
1. Connect its driver output to nodes that need to use AI models (like an Agent)

### Parameters

- **model**: The AI model to use (default is "gpt-4o")
- **response_format**: How you want responses formatted (options include "json_object")
- **seed**: A value to make responses more consistent between runs
- **stream**: Whether to receive responses as they're generated (true) or all at once (false)
- **temperature**: Controls randomness in responses (higher values = more creative, lower = more focused)
- **max_attempts_on_fail**: How many times to retry if there's an error
- **use_native_tools**: Whether to use the model's built-in tools
- **max_tokens**: Maximum length of responses
- **min_p**: Controls diversity of outputs (converted to top_p internally)

### Outputs

- **driver**: The configured Griptape Cloud driver that other nodes can use

## Example

Imagine you want to create an agent that uses GPT-4o through Griptape Cloud:

1. Add a GriptapeCloudPrompt to your workflow
1. Set "model" to "gpt-4o"
1. Connect the "driver" output to an Agent's "prompt_driver" input
1. Now that agent will use Griptape Cloud with your custom settings

Try these things:

1. Set "temperature" to 0.7 (for more creative responses)
1. Set "stream" to true or false (to see responses as they're generated, or just at once when done)

## Important Notes

- You need a valid Griptape API key set up in your environment as `GT_CLOUD_API_KEY`
- The default model is "gpt-4o"
- The min_p parameter is converted to top_p internally (top_p = 1 - min_p)

## Common Issues

- **Missing API Key**: Make sure your Griptape API key is properly set up
- **Connection Errors**: Check your internet connection and API key validity
