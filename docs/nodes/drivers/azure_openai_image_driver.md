# AzureOpenAiImageDriverNode

## What is it?
The AzureOpenAiImageDriverNode is a building block that sets up a connection to Microsoft Azure's OpenAI image generation service (DALL-E). Think of it as configuring a special artist that lives in Azure's cloud who can create images based on text descriptions.

## When would I use it?
Use this node when you want to:
- Generate images using Azure-hosted DALL-E models
- Meet specific security or compliance requirements by using Azure hosting
- Use your organization's Azure OpenAI resources for image generation

## How to use it

### Basic Setup
1. Add the AzureOpenAiImageDriverNode to your workspace
2. Connect it to your flow
3. Connect its output to nodes that need to generate images (like CreateImageNode)

### Optional Configuration
- **image_generation_model**: The DALL-E model to use (default is "dall-e-3")
- **image_deployment_name**: The name of your Azure deployment (default matches the model name)
- **size**: The size of images to generate (default is "1024x1024")
- **image_endpoint_env_var**: The name of your environment variable for the Azure endpoint
- **image_api_key_env_var**: The name of your environment variable for the Azure API key

### Outputs
- **driver**: The configured Azure OpenAI image driver that other nodes can use

## Example
Imagine you want to create images using Azure's DALL-E 3:

1. Add an AzureOpenAiImageDriverNode to your workflow
2. Set "image_generation_model" to "dall-e-3"
3. Set "size" to "1024x1792" for vertical images
4. Connect the "driver" output to a CreateImageNode's "driver" input
5. Now that node will generate images using Azure's DALL-E with your settings

## Important Notes
- You need valid Azure OpenAI DALL-E credentials set up in your environment:
  - `AZURE_OPENAI_DALL_E_3_API_KEY`
  - `AZURE_OPENAI_DALL_E_3_ENDPOINT`
- The node will automatically adjust image sizes based on model capabilities:
  - DALL-E 3 only supports 1024x1024, 1024x1792, and 1792x1024
  - DALL-E 2 only supports 256x256, 512x512, and 1024x1024

## Common Issues
- **Missing API Key or Endpoint**: Make sure your Azure OpenAI credentials are properly set up
- **Connection Errors**: Check your internet connection and API key validity
- **Invalid Size**: The node will adjust sizes to what the model supports, but it's best to select a compatible size