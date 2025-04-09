# GriptapeCloudPromptDriver

## What is it?

The GriptapeCloudPromptDriver is a building block that sets up a connection to Griptape Cloud's AI services. Think of it as configuring a special channel that your workflow can use to talk to AI models through Griptape's cloud platform.

## When would I use it?

Use this node when you want to:

- Use various AI models through the Griptape Cloud service
- Simplify model access with your Griptape API key
- Customize how your agents interact with AI models

## How to use it

### Basic Setup

1. Add the GriptapeCloudPromptDriver to your workspace
1. Connect it to your flow
1. Connect its output to nodes that need to use AI models (like RunAgent)

### Required Fields

None - the node uses default settings if you don't change anything

### Optional Configuration

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

1. Add a GriptapeCloudPromptDriver to your workflow
1. Set "model" to "gpt-4o"
1. Set "temperature" to 0.7 (for more creative responses)
1. Set "stream" to true (to see responses as they're generated)
1. Connect the "driver" output to a RunAgent's "prompt_driver" input
1. Now that agent will use Griptape Cloud with your custom settings

## Important Notes

- You need a valid Griptape API key set up in your environment as `GT_CLOUD_API_KEY`
- The default model is "gpt-4o"
- The min_p parameter is converted to top_p internally (top_p = 1 - min_p)

## Common Issues

- **Missing API Key**: Make sure your Griptape API key is properly set up
- **Connection Errors**: Check your internet connection and API key validity
- **Invalid Model**: Make sure you're using a model name that Griptape Cloud supports
