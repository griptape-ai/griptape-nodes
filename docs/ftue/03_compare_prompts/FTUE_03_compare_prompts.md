# Compare Prompts

Welcome to the fourth tutorial in our Griptape Nodes series! This guide explores how different prompting methods can significantly enhance your AI-generated images.

## What You'll Learn

In this tutorial, you will:

- Compare three different prompting approaches
- Understand the "Enhance Prompt" feature
- Create custom prompt enhancement flows
- See how agent nodes transform basic prompts into detailed instructions

## Navigate to the Landing Page

To begin this tutorial, return to the main landing page by clicking on the navigation element at the top of the interface.

## Open the Compare Prompts Example

On the landing page, locate and click on the **"Compare Prompts"** tile to open this example workflow.

<p align="center">
  <img src="../assets/compare_prompts_example.png" alt="Compare Prompts example">
</p>

## Understand the Workflow Structure

When the example loads, you'll see a workflow with multiple nodes:

<p align="center">
  <img src="../assets/compare_prompts_workflow.png" alt="Compare Prompts workflow">
</p>

This workflow contains:

- A text input node with a basic prompt ("a capybara eating with utensils")
- Three image generation nodes
- An agent node
- A merge texts node
- Connections showing how the data flows between components

We'll run each part of the workflow individually to compare the results of different prompting techniques.

## Comparing Different Prompting Methods

### Method 1: Basic Prompt

Let's start with the most straightforward approach:

1. Locate the text input node with our basic prompt: "a capybara eating with utensils"

1. Follow the connection to the first image generation node

1. Notice that "Enhance Prompt" is set to False on this node

1. Run just this node by clicking its individual run button

    <p align="center">
    <img src="../assets/basic_image_node.png" alt="Basic image node" width="450">
    </p>

Observe the resulting image. This shows how the AI interprets your direct, unmodified description.

### Method 2: Using Enhance Prompt Feature

For the second method, we'll use the same basic prompt but with Griptape's built-in enhancement:

1. Find the second image generation node that receives the same basic prompt

1. Notice that the "Enhance Prompt" feature is set to True

1. Run this node individually

    <p align="center">
    <img src="../assets/enhanced_prompt_image.png" alt="Enhanced prompt image" width="450">
    </p>

Compare this result with the first image. You should see a much more complex and artistic interpretation.

The difference is striking—same basic prompt, but the enhanced version produces a significantly more detailed and visually appealing image.

### Method 3: Bespoke Agent Enhancement

The third method demonstrates how we can create our own custom prompt enhancement:

1. Examine the flow that includes:

    - The same basic prompt
    - A "Merge Texts" node that combines our prompt with specific enhancement instructions
    - An agent node that processes these combined inputs

1. Look at the detailed instructions in "detail_prompt"

    <p align="center">
    <img src="../assets/detailed_instructions.png" alt="Detailed instructions">
    </p>

1. Run the agent node to see how it transforms our basic prompt

1. Examine the output in the display text node

    <p align="center">
    <img src="../assets/agent_node_output.png" alt="Agent node output">
    </p>

    You'll see that the agent has created a much more elaborate prompt that addresses all the specifications:

    - Unique details about the capybara
    - Specific time of day (late afternoon sunlight)
    - Depth of field information
    - Color palette guidance
    - Professional photography elements

1. Finally, run the third image generation node, which uses this agent-enhanced prompt with "Enhance Prompt" turned off

<p align="center">
  <img src="../assets/bespoke_prompt_image.png" alt="Bespoke Prompt Image" width="450">
</p>

Notice how this image contains specific details and artistic elements compared to the first, but is about the same level of sophistication as the second.

## Understanding What's Happening Behind the Scenes

Here's the key insight from this tutorial: When you toggle the "Enhance Prompt" feature to True, Griptape is essentially doing what we just demonstrated manually. It's:

1. Taking your basic prompt
1. Running it through an agent with enhancement instructions (verbatim what we wrote)
1. Using the enhanced output for image generation

By creating our own explicit enhancement flow, we gain full control over exactly how we want the prompt to be improved or changed.

## Applications and Best Practices

Based on what we've learned, consider these approaches for your own projects:

- Use basic prompts (with Enhance Prompt off) for quick, straightforward image generation
- Enable "Enhance Prompt" when you want general improvements with minimal effort
- Create custom agent-based enhancement flows when you need precise control over specific artistic elements or want to emphasize particular aspects like lighting, composition, or mood

## Summary

In this tutorial, you learned how to:

- Compare three different prompting approaches
- Use the built-in "Enhance Prompt" feature
- Create custom prompt enhancement flows with specific instructions
- See how agents can transform basic prompts into detailed, professional descriptions

These techniques demonstrate the power of prompt engineering—the art of crafting and refining prompts to achieve specific, high-quality outputs from AI systems.

## Next Up

In the next section: [Build a Photography Team](../04_photography_team/FTUE_04_photography_team.md), we'll learn about Rulesets, Tools, and converting Agents into tools to achieve even more sophisticated coordination!
