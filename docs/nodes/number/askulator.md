# Askulator

## What is it?

The Askulator is a natural language calculator node that can understand and solve mathematical problems expressed in plain English. It uses an AI model to interpret the question, perform the necessary calculations, and provide both the reasoning and the final answer.

## When would I use it?

Use this node when you want to:

- Solve mathematical problems expressed in natural language
- Get step-by-step reasoning for calculations
- Handle complex or ambiguous mathematical questions
- Perform calculations that require interpretation or estimation
- Get creative or approximate answers when exact numbers aren't available

## How to use it

### Basic Setup

1. Add the Askulator to your workflow
1. Enter your mathematical question in the "instruction" parameter
1. The node will process the question and provide:
    - A detailed reasoning of how it solved the problem
    - The final answer in the "result" output

### Parameters

- **instruction**: The mathematical question or problem to solve (supports natural language)
- **model**: The AI model to use for processing (default: gpt-4.1-mini)
- **result**: The final calculated answer
- **output**: The detailed reasoning and steps taken to solve the problem

### Outputs

- **result**: The final calculated answer
- **output**: The detailed reasoning and steps taken to solve the problem

## Example

Imagine you want to calculate something complex like "If I have 3 dozen eggs and give away a third, how many do I have left?":

1. Add an Askulator to your workflow
1. Enter the question in the "instruction" parameter
1. The node will:
    - Interpret that 3 dozen = 36 eggs
    - Calculate that a third of 36 is 12
    - Subtract 12 from 36
    - Provide the reasoning in the "output"
    - Give the final answer (24) in the "result"

## Implementation Details

The Askulator uses:

- A natural language processing model to understand questions
- The Calculator tool to perform precise calculations
- JSON output format to separate reasoning from the final answer
- Streaming updates to show progress in real-time

The node is designed to be creative and helpful, making reasonable estimates when exact numbers aren't available and providing clear explanations of its reasoning.
