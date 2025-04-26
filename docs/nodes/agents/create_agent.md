# Agent

## What is it?

The Agent node lets you configure an AI Agent with customizable capabilities like tools and rulesets. This node can create an Agent for immediate use given it's own prompt, or can be passed to other nodes' "agent" inputs.

## When would I use it?

Use this node when you want to:

- Create a configurable AI Agent from scratch
- Set up an Agent with specific tools and rulesets
- Prepare an Agent that can be reused across your workflow
- Get immediate responses from your agent using a custom prompt

## How to use it

### Basic Setup

1. Add the Agent to your workflow
1. Configure the agent's capabilities (tools and rulesets)

### Parameters

- **agent**: An existing Agent configuration (optional). If specified, it will use the existing Agent when prompting.
- **prompt**: The instructions or question you want to ask the Agent
- **additional_context**: String or key-value pairs providing additional context to the Agent
- **model**: The large language model to choose for your Agent. If you use the `prompt_model_config`, this will be ignored.
- **prompt_model_config**: The an external model configuration for how the Agent communicates with AI models.
- **tools**: Capabilities you want to give your Agent
- **rulesets**: Rules that tell your Agent what it can and cannot do

### Outputs

- **output**: The text response from your agent (if a prompt was provided)
- **agent**: The configured agent object, which can be connected to other nodes

## Example

Imagine you want to create an Agent that can write haikus based on prompt_context:

1. Add a KeyValuePair
1. Set the "key" to "topic" and "value" to "swimming"
1. Add an Agent
1. Set the Agent "prompt" to "Write me a haiku about {{topic}}"
1. Connect the KeyValuePair dictionary output to the Agent "prompt_context" input
1. Run the workflow
1. The Agent "output" will contain a haiku about swimming!

## Important Notes

- If you don't provide a prompt, the node will create the agent without running it and the output will contain exactly "Agent Created"
- The node supports both streaming and non-streaming prompt drivers
- Tools and rulesets can be provided as individual items or as lists
- The additional_context parameter allows you to provide additional_context to the agent as a string or dictionary of key/value pairs
- By default, you need a valid Griptape API key set up in your environment as `GT_CLOUD_API_KEY` for the node to work. Depending on the models you want to use, the keys you need will be different.
- When you pass an Agent from one node to another using the agent input/output pins, the conversation memory is maintained, which means:
    - The Agent "remembers" previous interactions in the same flow
    - Context from previous prompts influences how the Agent interprets new prompts
    - You can build multi-turn conversations across multiple nodes
    - The Agent can reference information provided in earlier steps of your workflow

## Common Issues

- **Missing Prompt Driver**: If not specified, the node will use the default prompt driver (It will use the GT_CLOUD_API_KEY and gpt-4o)
- **Streaming Issues**: If using a streaming prompt driver, ensure your flow supports handling streamed outputs
