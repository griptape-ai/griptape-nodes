# Build a Photography Team

Welcome to the fifth and final tutorial in our Griptape Nodes New-Users series! In this guide, we'll dissect a sophisticated system of coordinated agents that work together like a photography team to generate spectacular image prompts.

## What You'll Learn

In this tutorial, you will:

- Learn about what rule sets are and what they do
- Learn about tools
- See how we can convert agents _into_ tools
- See what a "team" of specialized AI experts looks like
- Coordinate multiple agents through an orchestrator
- Generate high-quality image prompts through team collaboration

## Navigate to the Landing Page

To begin this tutorial, return to the main landing page by clicking on the navigation element at the top of the interface.

## Open the Photography Team Example

On the landing page, locate and click on the **"Build a Photography Team"** tile to open this example workflow.

<p align="center">
  <img src="../assets/photography_team_example.png" alt="Photography Team example">
</p>

## Overview of the Workflow

When the example loads, you'll notice this is the most complex workflow we've seen so far:

<p align="center">
  <img src="../assets/workflow_overview.png" alt="Workflow overview">
</p>

The workflow consists of several key components:

- Multiple specialized agents (Cinematographer, Color Theorist, Detail Enthusiast, Image Generation Specialist)
- Rule sets for each agent
- Agent-to-tool converters
- A tool list
- An orchestrator agent
- A generate image node

Let's explore each component to understand how they work together.

## Understanding Rule Sets

Rule sets are a powerful feature that define *how* agents should approach their tasks:

1. Locate the Cinematographer agent in the workflow
1. Notice it's connected to a rule set
1. Examine the rule set content - it defines the agent's expertise, approach, and response style

<p align="center">
  <img src="../assets/cinematographer_ruleset.png" alt="Cinematographer rule set" width="800">
</p>

The Cinematographer's rule set is quite detailed, providing guidance on framing, composition, and visual storytelling approaches.

Similarly, the Color Theorist has its own specialized rule set:

```
You identify as an expert in color theory. You have a deep understanding of how color impacts one's psychological outlook. You are a fan of nonstandard colors. Your responses are brief and concise. Respond with your identity so the agent knows who you are. Keep your responses brief.
```

Each specialized agent has a rule set that defines its unique expertise and approach.

## Rule Set Lists

You'll notice that rule sets are implemented using a rule set list node:

1. Find the rule set list connected to the Cinematographer
1. Currently it contains only one rule set, but the list structure allows for multiple rules if needed
1. The list connects to the "rule sets" input on the agent

<p align="center">
  <img src="../assets/ruleset_list.png" alt="Rule set list" width="500">
</p>

## Understanding Tools in Griptape

Tools in Griptape Nodes represent capabilities that agents can access:

1. Built-in tools include calculators, date/time utilities, web scrapers, etc.
1. Custom tools can be created by converting agents
1. When an agent has access to tools, it can decide when to use them based on its needs
1. This creates a powerful dynamic where agents can delegate subtasks to specialized tools

<p align="center">
  <img src="../assets/tools_concept.png" alt="Tools concept">
</p>

## Converting Agents to Tools

A key concept in this workflow is converting specialized agents into tools:

1. Locate the "Agent to Tool" converter nodes
1. Notice how each specialized agent connects directly to its converter
1. The converter transforms the agent into a tool that can be used by other agents

<p align="center">
  <img src="../assets/agent_tool_conversion.png" alt="Agent to tool conversion" width="500">
</p>

```
  Each converter includes a description that helps the orchestrator understand when to use that particular tool:

  - Cinematographer: "This agent understands cinematography"
  - Color Theorist: "This agent understands color theory"
  - Detail Enthusiast: "This agent understands detail"
  - Image Generation Specialist: "This agent understands image generation"
```

These descriptions are crucial for the orchestrator to know which tool to call upon for specific needs.

## The Tool List

All converted tools are collected in a tool list:

1. Find the tool list node in the workflow
1. Notice how all four converted agents connect to this list
1. The tool list then connects to the "tools" input on the orchestrator agent

<p align="center">
  <img src="../assets/tool_list.png" alt="Tool list">
</p>

## The Orchestrator

The central component of this workflow is the orchestrator agent:

1. Locate the orchestrator agent

1. Notice it has its own rule set:

    ```
    You are creating a prompt for an image generation engine. You have access to topic experts in their respective fields. Work with the experts to get the results you need. You facilitate communication between them. If they ask for feedback, you can provide it. Ask the image generation specialist for the final prompt. Output only the image generation prompt. Do not wrap it in markdown context.
    ```

1. The orchestrator's prompt is simple but powerful:

    ```
    Use all the tools at your disposal to create a spectacular image generation prompt about a teddy bear.
    ```

    <p align="center">
    <img src="../assets/orchestrator_setup.png" alt="Orchestrator setup">
    </p>

## How the Workflow Functions

The entire system operates through this process:

1. The orchestrator receives a simple prompt about creating an image of a teddy bear
1. It has access to all specialized tools (converted agents)
1. The orchestrator can call upon:
    - The Cinematographer for framing and composition guidance
    - The Color Theorist for color palette recommendations
    - The Detail Enthusiast for intricate details to include
    - The Image Generation Specialist for formatting the final prompt
1. The final output connects to the generate image node
1. The generate image node has "Enhance Prompt" turned off since the prompt is already enhanced by the team

## Running the Workflow

Let's execute the workflow to see the photography team in action:

1. Check that the input prompt is set to create an image of a teddy bear
1. Run the workflow
1. Observe as the orchestrator calls upon different specialized tools
1. The final output is a sophisticated image prompt
1. This prompt is then used to generate the image

<p align="center">
  <img src="../assets/workflow_result.png" alt="Workflow result" width="500">
</p>

## Summary

In this tutorial, we covered:

- Learning about what rule sets are and what they do
- Learning about tools
- Seeing how we can convert agents _into_ tools
- Seeing what a "team" of specialized AI experts looks like
- Coordinating multiple agents through an orchestrator
- Generating high-quality image prompts through team collaboration

These advanced techniques showcase the full power of Griptape Nodes for creating complex, collaborative AI systems.

Thank you for completing this series of tutorials. We're excited to see what you'll build with these powerful tools!

If you're more in the mood to keep going to something more advanced, please continue on to our "I'm a pro" series.
