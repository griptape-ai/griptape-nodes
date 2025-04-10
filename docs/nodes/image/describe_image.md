# DescribeImage

## What is it?

The DescribeImage node uses Griptape Cloud API to analyze and describe the contents of an image. It processes an image artifact based on a provided prompt and generates a textual description of what the image contains.

## When would I use it?

Use the DescribeImage node when:

- You need to extract textual information from images
- You want to generate captions or descriptions for visual content
- You need to analyze the content of images programmatically
- You're building accessibility features that require image descriptions
- You want to create searchable text from image collections

## How to use it

### Basic Setup

1. Add a DescribeImage node to your workflow
1. Connect an Agent node to the agent parameter
1. Connect an ImageArtifact to the image parameter
1. Set a prompt describing what information you want about the image
1. Connect the output to nodes that can process text output

### Parameters

- **agent**: The agent used to describe the image (Agent or dict)
- **image**: The image artifact to be described (ImageArtifact)
- **prompt**: Instructions for how to describe the image (string)

### Outputs

- **output**: The textual description of the image (string)

## Important Notes

- You must set the `GT_CLOUD_API_KEY` environment variable for authentication with Griptape Cloud
- The quality of descriptions depends on the clarity of your prompt
- For best results, be specific about what aspects of the image you want described

## Common Issues

- Missing API key will result in a KeyError
- Unclear prompts may lead to generic or unhelpful descriptions
- Complex or ambiguous images may result in less accurate descriptions
- Very large images might take longer to process
