# AzureOpenAiChatPromptDriverNode

## What is it?
The AzureOpenAiChatPromptDriverNode is a building block that sets up a connection to Microsoft Azure's OpenAI service. Think of it as configuring a special channel to OpenAI models hosted on Azure's cloud.

## When would I use it?
Use this node when you want to:
- Use OpenAI models through Microsoft Azure (instead of directly through OpenAI)
- Meet specific security or compliance requirements by using Azure hosting
- Use your organization's Azure OpenAI resources

## How to use it

### Basic Setup
1. Add the AzureOpenAiChatPromptDriverNode to your workspace
2. Connect it to your flow
3. Connect its output to nodes that need to use Azure OpenAI (like RunAgentNode)

### Required Fields
None - the node uses default settings if you don't change anything

### Optional Configuration
- **model**: The OpenAI model to use (default is "gpt-4o")
- **response_format**: How you want responses formatted (options include "json_object")
- **seed**: A value to make responses more consistent between runs
- **temperature**: Controls randomness in responses (higher values = more creative, lower = more focused)
- **max_attempts_on_fail**: How many times to retry if there's an error
- **use_native_tools**: Whether to use OpenAI's built-in tools
- **max_tokens**: Maximum length of responses

### Outputs
- **driver**: The configured Azure OpenAI driver that other nodes can use

## Example
Imagine you want to create an agent that uses Azure-hosted GPT-4o:

1. Add an AzureOpenAiChatPromptDriverNode to your workflow
2. Set "model" to "gpt-4o"
3. Set "temperature" to 0.3 (for more focused responses)
4. Connect the "driver" output to a RunAgentNode's "prompt_driver" input
5. Now that agent will use Azure OpenAI with your custom settings

## Important Notes
- You need valid Azure OpenAI credentials set up in your environment:
  - `AZURE_OPENAI_API_KEY`
  - `AZURE_OPENAI_ENDPOINT`
- The default model and deployment is "gpt-4o"
- Some parameters that work with other providers (like min_p and top_k) aren't available for Azure OpenAI

## Common Issues
- **Missing API Key or Endpoint**: Make sure your Azure OpenAI credentials are properly set up
- **Connection Errors**: Check your internet connection and API key validity
- **Invalid Model**: Make sure you're using a model that's deployed to your Azure OpenAI resource