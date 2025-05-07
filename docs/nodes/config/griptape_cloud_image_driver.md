# GriptapeCloudImage

## What is it?

The GriptapeCloudImage node sets up a connection to Griptape Cloud's image generation service.

## When would I use it?

Use this node when you want to:

- Generate images using the Griptape Cloud service (you won't have to go register with OpenAI and get an api key)
- Create images with DALL-E 3 through Griptape's platform

## How to use it

### Basic Setup

1. Add a GriptapeCloudImage node to your workflow
1. Connect its driver output to nodes that need to generate images (like GenerateImage)

### Parameters

- **image_generation_model**: The model to use (default is "dall-e-3")
- **size**: The size of images to generate (default is "1024x1024")

### Outputs

- **image_model_config**: The configured Griptape Cloud image model configuration that other nodes can use

## Example

Imagine you want to create images using Griptape Cloud:

1. Add a GriptapeCloudImage node to your workflow
1. Set "size" to "1024x1792" for vertical images
1. Connect the "image_model_config" output to a GenerateImage's "image_model_config" input
1. Now that node will generate images using Griptape Cloud with your settings

## Important Notes

- You need a valid Griptape API key set up in your environment as `GT_CLOUD_API_KEY` (this should be automagic with your being in Griptape Nodes at all!)
- The node will automatically adjust image sizes based on model choice
- It should be noted, this is the default image_model_config for the GenerateImage node, and in fact should have no effect if plugged into that node.

## Common Issues

- **Connection Errors**: Check your internet connection and API key validity
- **Invalid Size**: The node will adjust sizes to what the model supports, but it's best to select a compatible size
