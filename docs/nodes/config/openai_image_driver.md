# OpenAiImage

## What is it?

The OpenAiImage node sets up a connection to OpenAI's image generation service (DALL-E).

## When would I use it?

Use this node when you want to:

- Generate images using OpenAI's DALL-E models
- Create visual content from text descriptions
- Connect image generation capabilities to your workflow

## How to use it

### Basic Setup

1. Add an OpenAiImage node to your workflow
1. Connect its driver output to nodes that can generate images (like GenerateImage)

### Parameters

- **model**: The model to use (default is "dall-e-3")
- **image_size**: The size of images to generate (default is "1024x1024")
- **style**: natural or vivid. Natural creates photorealistic images with natural lighting and textures, while vivid creates images with enhanced colors, contrast, and more dramatic compositions
- **quality**: Select the quality for image generation. Standard or HD.
- **background**: Select the background for image generation
- **moderation**: Standard or strict, regarding filtering for harmful or offensice content
- **output_format**: png, jpeg

### Outputs

- **image_model_config**: The configured OpenAI image model configuration that other nodes can use

## Example

Imagine you want to create images using OpenAI's DALL-E:

1. Add an OpenAiImage node to your workflow
1. Configure any available settings
1. Connect the "image_model_config" output to a GenerateImage's "image_model_config" input

## Important Notes

- You need a valid OpenAI API key set up in your environment as `OPENAI_API_KEY`
- This node is a simple wrapper around OpenAI's image generation capabilities
- The specific DALL-E model used will depend on what's configured in the underlying driver

## Common Issues

- **Missing API Key**: Make sure your OpenAI API key is properly set up
- **Connection Errors**: Check your internet connection and API key validity
- **Generation Limits**: Be aware of OpenAI's rate limits and usage quotas
