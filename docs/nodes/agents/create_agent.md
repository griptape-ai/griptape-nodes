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
2. Configure the agent's capabilities (tools and rulesets)

### Parameters

- **prompt**: The instructions or question you want to ask the Agent
- **prompt_driver**: The configuration for how the Agent communicates with AI models
- **tools**: Capabilities you want to give your Agent
- **rulesets**: Rules that tell your Agent what it can and cannot do
- **agent**: An existing Agent configuration (optional)
- **prompt_context**: Key-value pairs providing additional context to the Agent

### Outputs

- **output**: The text response from your agent (if a prompt was provided)
- **agent**: The configured agent object, which can be connected to other nodes

## Example

Imagine you want to create an Agent that can write haikus based on prompt_context:

1. Add a KeyValuePair
2. Set the "key" to "topic" and "value" to "swimming"
3. Add an Agent
4. Set the Agent "prompt" to "Write me a haiku about {{topic}}"
5. Connect the KeyValuePair dictionary output to the Agent "prompt_context" input
6. Run the workflow
7. The Agent "output" will contain a haiku about swimming!

## Important Notes

- If you don't provide a prompt, the node will create the agent without running it and the output will contain exactly "Agent Created"
- The node supports both streaming and non-streaming prompt drivers
- Tools and rulesets can be provided as individual items or as lists
- The prompt_context parameter allows you to provide additional context to the agent as a dictionary
- By default, you need a valid Griptape API key set up in your environment as `GT_CLOUD_API_KEY` for the node to work. Depending on the models you want to use, the keys you need will be different.
- When you pass an Agent from one node to another using the agent input/output pins, the conversation memory is maintained, which means:
    - The Agent "remembers" previous interactions in the same flow
    - Context from previous prompts influences how the Agent interprets new prompts
    - You can build multi-turn conversations across multiple nodes
    - The Agent can reference information provided in earlier steps of your workflow

## Common Issues

- **Missing Prompt Driver**: If not specified, the node will use the default prompt driver (It will use the GT_CLOUD_API_KEY and gpt-4o)
- **Streaming Issues**: If using a streaming prompt driver, ensure your flow supports handling streamed outputs