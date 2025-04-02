# GriptapeCloudImageDriverNode

## What is it?
The GriptapeCloudImageDriverNode is a building block that sets up a connection to Griptape Cloud's image generation service. Think of it as configuring a special artist in the cloud who can create images based on text descriptions.

## When would I use it?
Use this node when you want to:
- Generate images using the Griptape Cloud service
- Create images with DALL-E 3 through Griptape's platform
- Simplify the image generation process with your API key

## How to use it

### Basic Setup
1. Add the GriptapeCloudImageDriverNode to your workspace
2. Connect it to your flow
3. Connect its output to nodes that need to generate images (like CreateImageNode)

### Optional Configuration
- **image_generation_model**: The model to use (default is "dall-e-3")
- **image_deployment_name**: The deployment name (default matches the model name)
- **size**: The size of images to generate (default is "1024x1024")

### Outputs
- **driver**: The configured Griptape Cloud image driver that other nodes can use

## Example
Imagine you want to create images using Griptape Cloud:

1. Add a GriptapeCloudImageDriverNode to your workflow
2. Set "size" to "1024x1792" for vertical images
3. Connect the "driver" output to a CreateImageNode's "driver" input
4. Now that node will generate images using Griptape Cloud with your settings

## Important Notes
- You need a valid Griptape API key set up in your environment as `GT_CLOUD_API_KEY`
- Currently, only DALL-E 3 is supported through this driver
- The node will automatically adjust image sizes based on model capabilities:
  - DALL-E 3 only supports 1024x1024, 1024x1792, and 1792x1024

## Common Issues
- **Missing API Key**: Make sure your Griptape API key is properly set up
- **Connection Errors**: Check your internet connection and API key validity
- **Invalid Size**: The node will adjust sizes to what the model supports, but it's best to select a compatible size