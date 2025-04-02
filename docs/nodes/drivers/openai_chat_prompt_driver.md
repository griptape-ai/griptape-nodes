# OpenAiChatPromptDriverNode

## What is it?
The OpenAiChatPromptDriverNode is a building block that sets up a direct connection to OpenAI's models like GPT-4o. Think of it as configuring a special channel that your workflow can use to talk to OpenAI's powerful language models.

## When would I use it?
Use this node when you want to:
- Use OpenAI's models in your workflow
- Customize how your agents interact with models like GPT-4o
- Control specific settings for OpenAI's responses

## How to use it

### Basic Setup
1. Add the OpenAiChatPromptDriverNode to your workspace
2. Connect it to your flow
3. Connect its output to nodes that need to use OpenAI (like RunAgentNode)

### Required Fields
None - the node uses default settings if you don't change anything

### Optional Configuration
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

1. Add an OpenAiChatPromptDriverNode to your workflow
2. Set "model" to "gpt-4o"
3. Set "temperature" to 0.2 (for more focused, deterministic responses)
4. Set "max_tokens" to 2000 (for longer responses)
5. Connect the "driver" output to a RunAgentNode's "prompt_driver" input
6. Now that agent will use OpenAI with your custom settings

## Important Notes
- You need a valid OpenAI API key set up in your environment as `OPENAI_API_KEY`
- The default model is "gpt-4o"
- The min_p parameter is converted to top_p internally (top_p = 1 - min_p)
- Unlike some other drivers, OpenAI doesn't support the top_k parameter

## Common Issues
- **Missing API Key**: Make sure your OpenAI API key is properly set up
- **Connection Errors**: Check your internet connection and API key validity
- **Invalid Model**: Make sure you're using a model name that OpenAI supports