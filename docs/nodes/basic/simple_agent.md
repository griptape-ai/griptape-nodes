# SimpleAgent

## What is it?

The SimpleAgent is a streamlined building block that lets you run an AI agent that was created earlier in your workflow. Think of it as giving instructions to an assistant that's already been set up.

## When would I use it?
Use this node when you want to:
- Continue using an agent that was created by another node
- Ask different questions to the same agent
- Chain multiple instructions to the same agent

## How to use it

### Basic Setup

1. Add the SimpleAgent to your workspace
1. Connect it to your flow
1. Connect it to an existing agent (usually from a RunAgent)

### Required Fields
- **agent**: The agent to run (connected from another node that created an agent)
- **prompt**: The instructions or question you want to ask the agent

### Outputs
- **output**: The text response from your agent
- **agent**: The agent itself, which can be connected to other nodes

## Example
Imagine you already have an agent that knows about your project and you want to ask it another question:

1. Connect the "agent" output from a previous RunAgent to the "agent" input of the SimpleAgent
1. In the "prompt" field, type: "Summarize what we've discussed so far"
1. Run the node
1. The "output" will contain the agent's summary

## Important Notes
- You need a valid Griptape API key set up in your environment as `GT_CLOUD_API_KEY`
- If no agent is connected, a new one will be created automatically
- If you don't provide a prompt, the output will just say "Agent Created"

## Common Issues
- **Missing API Key**: Make sure your Griptape API key is properly set up
- **No Response**: Check that you've entered a prompt in the prompt field
- **Wrong Agent**: Verify you've connected the correct agent to this node