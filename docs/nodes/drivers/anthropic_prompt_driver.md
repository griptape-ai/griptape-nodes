# AnthropicPrompt

## What is it?

The AnthropicPrompt node sets up a connection to Anthropic's AI models (like Claude).

## When would I use it?

Use this node when you want to:

- Use Anthropic's chat models in your workflow
- Customize how your agents interact with Anthropic models
- Control specific settings for Anthropic model responses

## How to use it

### Basic Setup

1. Add an AnthropicPrompt node to your workflow
1. Connect its output to nodes that can use Anthopic prompt models like Claude (lfor instance, an Agent!)

### Parameters

- **model**: The model to use (default is "claude-3-7-sonnet-latest")
- **stream**: Whether to receive responses as they're generated (true) or all at once (false)
- **temperature**: Controls randomness in responses (higher values = more creative, lower = more focused)
- **max_attempts_on_fail**: How many times to retry if there's an error
- **use_native_tools**: Whether to use Anthropic's built-in tools
- **max_tokens**: Maximum length of responses
- **min_p**: Controls diversity of outputs (similar to temperature)
- **top_k**: Controls focus on most likely tokens

### Outputs

- **driver**: The configured Anthropic driver that other nodes can use

## Example

To create an agent that uses Anthropic models with specific settings:

1. Add an AnthropicPrompt to your workflow
1. Connect the "driver" output to an Agent's "prompt_driver" input
1. Now that agent will use Claude with your custom settings

Things to try:

1. Try changing the "model" from "claude-3-5-sonnet-latest"
1. Set "temperature" to 0.7 (for more creative responses)
1. Set "max_tokens" to 2000 (for longer responses)

## Important Notes

- You need a valid Anthropic API key set up in your environment as `ANTHROPIC_API_KEY`
- The default model is "claude-3-5-sonnet-latest"
- The node checks if your API key is valid during setup

## Common Issues

- **Missing API Key**: Make sure your Anthropic API key is properly set up in app settings
- **Connection Errors**: Check your internet connection and API key validity
