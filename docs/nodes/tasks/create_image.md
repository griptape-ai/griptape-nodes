# CreateImage

## What is it?

The CreateImage node generates images based on text prompts using Griptape Cloud services. It integrates with Griptape Cloud Image Generation Driver and Prompt Driver to transform textual descriptions into high-quality images.

## When would I use it?

Use the CreateImage node when:

- You need to generate images dynamically in your workflow
- You want to create visual content based on text descriptions
- You're building applications that require programmatic image generation
- You need to visualize concepts described in natural language

## How to use it

### Basic Setup

1. Add a CreateImage node to your workflow
2. Connect an Agent node to the agent parameter
3. Set the image_generation_driver parameter (or use the default)
4. Provide a text prompt describing the image you want to generate
5. Connect the output to nodes that can process image artifacts

### Parameters

**Inputs:**
- **agent**: The agent responsible for handling prompt and image generation tasks (Agent or dict)
- **image_generation_driver**: The driver used for image generation (defaults to None)
- **prompt**: Text description of the image to generate (string)
- **enhance_prompt**: Whether to enhance the prompt for better image quality (boolean, defaults to True)

**Outputs:**
- **output**: The generated image as an ImageArtifact

## Example

A simple workflow to generate and save an image:

1. Add a CreateImage node to your workflow
2. Connect an Agent node to the agent parameter
3. Set the prompt to "A serene mountain landscape at sunset with a lake reflecting the orange sky"
4. Connect the output to a SaveImage node to store the generated image

## Important Notes

- You must set the `GT_CLOUD_API_KEY` environment variable for authentication with Griptape Cloud
- The node uses 'dall-e-3' as the default model and 'hd' as the default quality
- Enhanced prompts can improve image quality but may interpret your prompt differently than expected

## Common Issues

- Missing API key will result in a KeyError