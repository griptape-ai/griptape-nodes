# CreateImage

## What is it?

The CreateImage is a building block that lets you generate images using AI. Think of it as having an artist on call who can create images based on your description.

## When would I use it?

Use this node when you want to:

- Create images from text descriptions
- Generate visual content for your projects
- Illustrate concepts or ideas with AI-generated images

## How to use it

### Basic Setup

1. Add the CreateImage to your workspace
1. Connect it to your flow

### Required Fields

- **prompt**: The description of the image you want to create (e.g., "a sunset over mountains with a lake")

### Optional Configuration

- **agent**: An existing AI agent to use (if you already have one set up)
- **driver**: Advanced - A custom image generation system (most users can leave this empty)
- **output_file**: A specific filename for saving the image
- **output_dir**: A folder where you want to save the image

### Outputs

- **output**: The generated image as an artifact that can be used by other nodes
- **agent**: The agent that was used to create the image

## Example

Imagine you want to create an image of a friendly robot:

1. Add a CreateImage
1. In the "prompt" field, type: "A friendly robot helping a child with homework"
1. Run the node
1. The image will be generated and saved in the Images folder by default

## Important Notes

- You need a valid Griptape API key set up in your environment as `GT_CLOUD_API_KEY`
- By default, images are saved to an "Images" folder in your workspace
- The default AI model used is "dall-e-3" which creates high-quality images

## Common Issues

- **Missing API Key**: Make sure your Griptape API key is properly set up
- **No Image Generated**: Check that your prompt is clear and descriptive
- **Cannot Find Image**: Look in the default Images directory or check the path you specified
