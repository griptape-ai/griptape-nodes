# CoherePromptDriver

## What is it?

The CoherePromptDriver is a building block that sets up a connection to Cohere's AI models. Think of it as configuring a special channel that your workflow can use to talk to Cohere's language models.

## When would I use it?

Use this node when you want to:

- Use Cohere's AI models in your workflow
- Take advantage of Cohere's specific capabilities
- Customize how your agents interact with Cohere's models

## How to use it

### Basic Setup

1. Add the CoherePromptDriver to your workspace
2. Connect it to your flow
3. Connect its output to nodes that need to use Cohere (like RunAgent)

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

Imagine you want to create an agent that uses Cohere with specific settings:

1. Add a CoherePromptDriver to your workflow
1. Set "model" to "command-r-plus"
1. Set "max_tokens" to 1000 (for moderate length responses)
1. Connect the "driver" output to a RunAgent's "prompt_driver" input
1. Now that agent will use Cohere with your custom settings

## Important Notes

- You need a valid Cohere API key set up in your environment as `COHERE_API_KEY`
- The default model is "command-r-plus"
- The node checks if your API key is valid during setup

## Common Issues

- **Missing API Key**: Make sure your Cohere API key is properly set up
- **Connection Errors**: Check your internet connection and API key validity
- **Invalid Model**: Make sure you're using a model name that Cohere supports
