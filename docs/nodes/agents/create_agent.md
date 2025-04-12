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
2. Configure the agent's capabilities (tools and rulesets)
3. Connect it to your flow

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

Imagine you want to create an agent that can search the web and summarize information:

1. Add a CreateAgent
2. Add a web search tool to the "tools" parameter
3. Add context information to "prompt_context" if needed (such as {"topic": "artificial intelligence"})
4. In the "prompt" field, type: "Search for the latest developments in AI and summarize them"
5. Run the node
6. The "output" will contain the agent's response with the summary
7. The "agent" output can be connected to other nodes that need to use this configured agent

## Important Notes

- If you don't provide a prompt, the node will create the agent without running it and the output will contain exactly "Agent Created"
- The node supports both streaming and non-streaming prompt drivers
- Tools and rulesets can be provided as individual items or as lists
- The prompt_context parameter allows you to provide additional context to the agent as key-value pairs
- You need a valid Griptape API key set up in your environment as `GT_CLOUD_API_KEY`
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

- **Configuration Mismatch**: Ensure your tools and rulesets are compatible with each other
- **Missing Prompt Driver**: If not specified, the node will use a default prompt driver
- **Streaming Issues**: If using a streaming prompt driver, ensure your flow supports handling streamed outputs