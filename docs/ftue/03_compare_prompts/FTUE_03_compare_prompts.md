# Lesson 4: Compare Prompts

Welcome to our fourth Griptape Nodes tutorial! Building on what you already know about multi-agent systems and image generation, we're diving into the exciting world of prompt engineering. You'll discover how to use ready-made solutions and create your own prompt-building workflows to get consistently better results. Plus, we'll peek behind the curtain to see how the "Enhance Prompt" feature actually works its magic!

## What we'll cover

In this tutorial, we will:

- Compare three different prompting approaches for image generation
- Understand the "Enhance Prompt" feature
- Learn about custom prompt enhancement flows

## Navigate to the Landing Page

To begin this tutorial, return to the main landing page by clicking on the Griptape Nodes logo at the top left of the interface.

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

- Two TextInput node
  - basic_prompt
  - detail_prompt
- A MergeTexts node, assemble_prompt
- Three GeerateImage nodes:
  - basic_image
  - enhanced_prompt_image
  - bespoke_prompt_image
- An agent node, bespoke_prompt

We'll run each part of the workflow individually to compare the results of different prompting techniques.

## Comparing Different Prompting Methods

### Method 1: Basic Prompt

Let's start with the most straightforward approach:

1. Locate the TextInput node with our simple prompt: "A capybara eating with utensils"

1. Follow the connection to the first GenerateImage node

1. Notice that **Enhance Prompt** is set to **False** on this node

1. Run just this node by clicking the **run node** button at the top right of the node

    <p align="center">
    <img src="../assets/basic_image_node.png" alt="Basic image node" width="450">
    </p>

Observe the resulting image. This shows how the AI interprets your direct, simple prompt.

### Method 2: Using Enhance Prompt Feature

For the second method, we'll use the same simple prompt but with use the GenerateImage's built-in enhancement:

1. Find the second GenerateImage node that receives the same simple prompt

1. Notice that **Enhance Prompt** is set to **True** on this node

1. Run this node using the it's **Run Node** button

    <p align="center">
    <img src="../assets/enhanced_prompt_image.png" alt="Enhanced prompt image" width="450">
    </p>

Compare this result with the first image. You should see a much more complex and artistic interpretation.

The difference is striking—same simple prompt, but the enhanced version produces a significantly more detailed and visually appealing image.

### Method 3: Bespoke Agent-Enhanced Prompt

The third method demonstrates how we can create our own custom prompt enhancement:

1. Take a look at how we're uing the MergeTexts node and an agent to create a prompt:
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

Here's the key insight: When you toggle the "Enhance Prompt" feature to True, Griptape is essentially doing what we just demonstrated manually. It's:

1. Taking your basic prompt
1. Running it through an agent with enhancement instructions (verbatim what we wrote)
1. Using the enhanced output for image generation

By creating our own explicit enhancement flow, we gain full control over exactly how we want the prompt to be improved or changed.

## Applications and Best Practices

Based on what we've learned, consider these approaches for your own projects:

- Use basic prompts (with Enhance Prompt off) for quick, straightforward image generation
- Enable "Enhance Prompt" when you want general improvements with minimal effort
- Create custom agent-based enhancement flows when you need precise control over specific artistic elements or want to emphasize particular aspects.

## Summary

In this tutorial, we covered:

- Three different prompting approaches for image generation
- Learned about the "Enhance Prompt" feature
- Learned about custom prompt enhancement flows

These techniques demonstrate the power of prompt engineering—the art of crafting and refining prompts to achieve specific, high-quality outputs from AI systems.

## Next Up

In the next section: [Lesson 5: Build a Photography Team](../04_photography_team/FTUE_04_photography_team.md), we'll learn about Rulesets, Tools, and converting Agents into tools to achieve even more sophisticated coordination!
