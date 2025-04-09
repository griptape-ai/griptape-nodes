# Reroute

## What is it?

The Reroute node is a utility node that acts as a connection point for rerouting data between different parts of your workflow. It dynamically adjusts the allowed types of its parameters based on the connections established, making it easier to organize complex workflows.

In short, it's just a way to shape your connections between nodes.

## When would I use it?

Use the Reroute node when:

- You need to organize complex workflows with many crossing connections
- You want to improve the visual clarity of your workflow
- You're working with connections that need to span across distant parts of your workflow
- You need to bundle multiple connections together
- You want to create a cleaner, more maintainable workflow layout

## How to use it

### Basic Setup

1. Add a Reroute node to your workflow
2. Connect the source node output to the Reroute node's input
3. Connect the Reroute node's output to the target node's input
4. The node will automatically adapt to pass through the correct data types

### Parameters

**Inputs/Outputs:**
- **passThru**: A parameter that can function as both input and output, dynamically adapting its allowed types based on connections

## Important Notes

- The Reroute node does not modify the data passing through it
- It automatically adjusts its parameter types based on the connections made
- It can help improve workflow organization and readability
- Multiple Reroute nodes can be chained together for complex routing needs
