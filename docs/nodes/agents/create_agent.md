# CreateAgent

## What is it?

CreateAgent lets you configure an AI agent with customizable capabilities like tools and rulesets. This node focuses on setting up an agent with specific configurations that can be used immediately or passed to other nodes.

## When would I use it?

Use this node when you want to:

- Create a configurable AI agent from scratch
- Set up an agent with specific tools and rulesets
- Prepare an agent that can be reused across your workspace
- Get immediate responses from your agent using a custom prompt

## How to use it

### Basic Setup

1. Add the CreateAgent to your workspace
1. Configure the agent's capabilities (tools and rulesets)
1. Connect it to your flow

### Parameters

- **prompt**: The instructions or question you want to ask the agent
- **prompt_driver**: The configuration for how the agent communicates with AI models
- **tools**: Capabilities you want to give your agent
- **rulesets**: Rules that tell your agent what it can and cannot do
- **agent**: An existing agent configuration (optional)
- **prompt_context**: Key-value pairs providing additional context to the agent

### Outputs

- **output**: The text response from your agent (if a prompt was provided)
- **agent**: The configured agent object, which can be connected to other nodes

## Example

Imagine you want to create an agent that can write haikus based on prompt_context:

1. Add a KeyValuePair
1. Set the "key" to "topic" and "value" to "swimming"
1. Add a CreateAgent
1. Set the "prompt" to "write me a haiku about {{topic}}"
1. Connect the KeyValuePair dictionary output to the CreateAgent prompt_context input
1. Run the workflow
1. The CreateAgent "output" will contain a haiku about swimming!

## Important Notes

- If you don't provide a prompt, the node will create the agent without running it and the output will contain exactly "Agent Created"
- The node supports both streaming and non-streaming prompt drivers
- Tools and rulesets can be provided as individual items or as lists
- The prompt_context parameter allows you to provide additional context to the agent as a dictionary
- By default, you need a valid Griptape API key set up in your environment as `GT_CLOUD_API_KEY` for the node to work. Depending on the models you want to use, the keys you need will be different.
- CreateAgent is designed for detailed configuration while RunAgent is for execution. Use CreateAgent when you need to:
    - Configure an agent once and run it multiple times with different prompts
    - Set up complex combinations of tools and rulesets
    - Create specialized agents for different tasks in your workflow
- When you pass an agent from one node to another using the agent output pin, the conversation memory is maintained, which means:
    - The agent "remembers" previous interactions in the same flow
    - Context from previous prompts influences how the agent interprets new prompts
    - You can build multi-turn conversations across multiple nodes
    - The agent can reference information provided in earlier steps of your workflow

## Common Issues

- **Missing Prompt Driver**: If not specified, the node will use the default prompt driver (It will use the GT_CLOUD_API_KEY and gpt-4o)
- **Streaming Issues**: If using a streaming prompt driver, ensure your flow supports handling streamed outputs
