# AnthropicPromptDriverNode

## What is it?
The AnthropicPromptDriverNode is a building block that sets up a connection to Anthropic's AI models (like Claude). Think of it as configuring a special phone line that your workflow can use to talk to Claude.

## When would I use it?
Use this node when you want to:
- Use Anthropic's Claude models in your workflow
- Customize how your agents interact with Claude
- Control specific settings for Claude's responses

## How to use it

### Basic Setup
1. Add the AnthropicPromptDriverNode to your workspace
2. Connect it to your flow
3. Connect its output to nodes that need to use Claude (like RunAgentNode)

### Required Fields
None - the node uses default settings if you don't change anything

### Optional Configuration
- **model**: The Claude model to use (default is "claude-3-5-sonnet-latest")
- **stream**: Whether to receive responses as they're generated (true) or all at once (false)
- **temperature**: Controls randomness in responses (higher values = more creative, lower = more focused)
- **max_attempts_on_fail**: How many times to retry if there's an error
- **use_native_tools**: Whether to use Claude's built-in tools
- **max_tokens**: Maximum length of responses
- **min_p**: Controls diversity of outputs (similar to temperature)
- **top_k**: Controls focus on most likely tokens

### Outputs
- **driver**: The configured Anthropic driver that other nodes can use

## Example
Imagine you want to create an agent that uses Claude with specific settings:

1. Add an AnthropicPromptDriverNode to your workflow
2. Set "model" to "claude-3-5-sonnet-latest"
3. Set "temperature" to 0.7 (for more creative responses)
4. Set "max_tokens" to 2000 (for longer responses)
5. Connect the "driver" output to a RunAgentNode's "prompt_driver" input
6. Now that agent will use Claude with your custom settings

## Important Notes
- You need a valid Anthropic API key set up in your environment as `ANTHROPIC_API_KEY`
- The default model is "claude-3-5-sonnet-latest"
- The node checks if your API key is valid during setup

## Common Issues
- **Missing API Key**: Make sure your Anthropic API key is properly set up
- **Connection Errors**: Check your internet connection and API key validity
- **Invalid Model**: Make sure you're using a model name that Anthropic supports