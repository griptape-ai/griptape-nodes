# RunAgent

## What is it?

RunAgent executes prompts on an existing AI agent or creates a new one with default settings. This node focuses on running prompts and getting responses rather than configuring complex agent capabilities.

## When would I use it?

Use this node when you want to:

- Quickly run a prompt on an AI agent
- Execute tasks with an existing agent configuration
- Get text responses from an AI based on your instructions
- Use a pre-configured agent in a workflow

## How to use it

### Basic Setup

1. Add the RunAgent to your workspace
2. Connect it to your flow
3. Provide a prompt or connect an existing agent

### Parameters

- **prompt**: The instructions or question you want to ask the agent
- **agent**: An existing agent configuration (optional)
- **prompt_context**: Key-value pairs providing additional context to the agent

### Outputs

- **output**: The text response from your agent
- **agent**: The agent object itself, which can be connected to other nodes

## Example

Imagine you want to ask an AI agent a question:

1. Add a RunAgent
2. Add contextual information to "prompt_context" if needed (such as {"user_location": "New York"})
3. In the "prompt" field, type: "Explain quantum computing in simple terms"
4. Run the node
5. The "output" will contain the agent's explanation of quantum computing

Or with an existing agent:

1. Connect an agent output from another node to the RunAgent's "agent" input
2. Provide a new prompt and any additional context
3. Run the node to get a response using the connected agent's capabilities

## Important Notes

- If no agent is provided, the node will use your GT_CLOUD_API_KEY and gpt-4o
- The node automatically uses the Griptape Cloud API with streaming enabled
- You need a valid Griptape API key set up in your environment as `GT_CLOUD_API_KEY`
- If you don't provide a prompt, the node will just create the agent without running it and the output will contain exactly "Agent Created"
- RunAgent is more execution-focused while CreateAgent is configuration-focused. Use RunAgent when you:
  - Need to quickly run a prompt without complex configuration
  - Want to use a pre-configured agent that was created earlier in your workflow
  - Are building a chain of conversational interactions
- When connecting multiple RunAgent nodes by passing the agent output to the next node's agent input:
  - Conversation memory is preserved throughout the chain
  - The agent will "remember" all previous prompts and responses
  - Context builds up across nodes, allowing for follow-up questions
  - References to earlier information will be understood by the agent
  - This enables building complex multi-turn conversations across your workflow

## Common Issues

- **Missing API Key**: Make sure your Griptape API key is properly set up as the environment variable
- **No Response**: Check that you've entered a prompt in the prompt field
- **Streaming Issues**: If the streaming process is interrupted, you might receive a partial response
- **Context Errors**: Ensure that prompt_context contains valid key-value pairs in dictionary format