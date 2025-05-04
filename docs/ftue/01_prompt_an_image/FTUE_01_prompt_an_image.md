# Prompt an Image

Welcome to the second tutorial in our Griptape Nodes series! In this guide, you'll learn how to generate images using AI through the powerful GenerateImage node.

## What we'll cover

In this tutorial, you will:

- Learn how to open saved workflows
- Learn about the GenerateImage node
- Generate images using text prompts

## Navigate to the Landing Page

To begin this tutorial, you'll need to return to the main landing page. Click on the navigation element at the top of the interface to go back to where all the example workflows are displayed.

<p align="center">
  <img src="../assets/nav_bar.png" alt="Nav Bar" width="300">
</p>

## Open the Image Prompt Example

On the landing page, locate and click on the **"Prompt an Image"** tile to open this example workflow.

<p align="center">
  <img src="../assets/prompt_image_example.png" alt="Prompt an Image example">
</p>

## Understand the GenerateImage Node

When the example loads, you'll notice it consists of just a single node. Don't be fooled by its simplicity – this node is one of the most powerful tools in Griptape Nodes and will likely feature prominently in your future flows.

<p align="center">
  <img src="../assets/generate_image_node.png" alt="GenerateImage node" width="300">
</p>

This node has been configured to handle many tasks that would typically require a more complex flow, making it perfect for getting started with AI image generation.

## Generate Images Using Text Prompts

The primary point of interaction for this node is the text prompt field where you describe what image you want the AI to create.

To generate your first image:

  1. Locate the text prompt field in the node
  1. Type a description for the image you want to create

    <p align="center">
      <img src="../assets/text_prompt_field.png" alt="Text prompt field" width="300">
    </p>

  1. Now, run your node.  There are two ways to do this:

    - Click the "Run Workflow" button at the top of the editor.  This executes the entire workflow from start to finish.  All nodes will be processed in sequence according to their connections

    - Click the "Run Node" button in the top right corner of a specific node. This executes only that particular node and any upstream nodes required for its inputs.  Useful for testing or debugging specific parts of your workflow

    The difference is in scope - the first option runs everything, while the second option runs just the selected node and what it needs.

## Experiment with Different Descriptions

Let's try generating some images with different prompts:

1. **First Example**: The workflow loads with "A potato making an oil painting" in the prompt field. Run the flow

    <p align="center">
    <img src="../assets/potato_painting.png" alt="Potato painting result">
    </p>

1. **Second Example**: Change the prompt to "A potato doing aerobics in 70s workout attire" and run the flow again

    <p align="center">
    <img src="../assets/potato_aerobics.png" alt="Potato aerobics result">
    </p>

Notice how dramatically different the results are just by changing a few words in your prompt. This demonstrates the flexibility and power of the GenerateImage node. Anything you can describe, you can generate.

## Summary

In this tutorial, you learned how to:

- Learn how to open saved workflow
- Learn the GenerateImage node
- Generate images using text prompts

The GenerateImage node is a fundamental building block for creative flows in Griptape Nodes. As you progress, you'll discover how to combine it with other nodes to develop even more powerful applications.

## Next Up

In the next section: [Coordinating Agents](../02_translator/FTUE_02_translator.md), we'll learn how to get AIs to bucket-brigade through flows!
