# RunAgent

## What is it?

The RunAgent is a building block in our visual scripting system that lets you create and run an AI agent. Think of it as setting up a smart assistant that can perform tasks for you based on what you tell it to do.

## When would I use it?
Use this node when you want to:
- Create an AI agent that can respond to prompts
- Set up an agent with specific capabilities (tools)
- Get text responses from an AI based on your instructions

## How to use it

### Basic Setup

1. Add the RunAgent to your workspace
1. Connect it to your flow

### Required Fields
- **prompt**: The instructions or question you want to ask the agent

### Optional Configuration

#### Agent Config Group
- **prompt_model**: The AI model to use (default is "gpt-4o")
- **prompt_driver**: Advanced - A custom way to communicate with the AI model (most users can leave this empty)

#### Agent Tools Group
- **tool**: A single capability you want to give your agent
- **tool_list**: Multiple capabilities for your agent
- **ruleset**: Rules that tell your agent what it can and cannot do

### Outputs
- **output**: The text response from your agent
- **agent**: The agent object itself, which can be connected to other nodes

## Example
Imagine you want to create an agent that can answer questions about the weather:

1. Add a RunAgent
1. In the "prompt" field, type: "What's the weather like in New York today?"
1. Run the node
1. The "output" will contain the agent's response about the weather

## Important Notes
- You need a valid Griptape API key set up in your environment as `GT_CLOUD_API_KEY`
- If you don't provide a prompt, the node will just create the agent without running it
- The default AI model is "gpt-4o" but you can change this in the Agent Config

## Common Issues
- **Missing API Key**: Make sure your Griptape API key is properly set up
- **No Response**: Check that you've entered a prompt in the prompt field
- **Error in Response**: The agent might encounter issues if it doesn't have the right tools for your request