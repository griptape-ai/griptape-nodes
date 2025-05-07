# GrokImage

## What is it?

The GrokImage node sets up a connection to Grok's image generation service (DALL-E).

## When would I use it?

Use this node when you want to:

- Generate images using Grok's DALL-E models
- Create visual content from text descriptions
- Connect image generation capabilities to your workflow

## How to use it

### Basic Setup

1. Add an GrokImage node to your workflow
1. Connect its driver output to nodes that can generate images (like GenerateImage)

### Parameters

- **image_generation_model**: The model to use (default is "grok-2-image-1212")

### Outputs

- **image_model_config**: The configured Grok image model configuration that other nodes can use

## Example

Imagine you want to create images using Grok:

1. Add an GrokImage node to your workflow
1. Configure any available settings
1. Connect the "image_model_config" output to a GenerateImage's "image_model_config" input

## Important Notes

- You need a valid Grok API key set up in your environment as `GROK_API_KEY`, available from: https://console.x.ai
- This node is a simple wrapper around Grok's image generation capabilities

## Common Issues

- **Missing API Key**: Make sure your Grok API key is properly set up
- **Connection Errors**: Check your internet connection and API key validity
- **Generation Limits**: Be aware of Grok's rate limits and usage quotas
