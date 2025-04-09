# CreateImage Node

## Overview

The `CreateImage` node is a control node designed to generate images using the Griptape Cloud services. It leverages the capabilities of the Griptape Cloud Image Generation Driver and the Griptape Cloud Prompt Driver to produce high-quality images based on user-defined prompts.

## When would I use it?

Use the `CreateImage` node when you need to generate images programmatically within a workflow. This node is particularly useful for applications requiring dynamic image creation based on textual descriptions or prompts.

## Basic Setup

1. **Add the Node**: Integrate the `CreateImage` node into your workflow.
2. **Configure Parameters**: Set up the necessary parameters such as `agent`, `image_generation_driver`, and `prompt`.

## Configuration Options

- **agent**: 
  - **Type**: `Agent` or `dict`
  - **Description**: The agent responsible for managing the prompt and image generation tasks.
  - **Modes**: Input, Output

- **image_generation_driver**: 
  - **Type**: `Image Generation Driver`
  - **Description**: The driver used for image generation.
  - **Default**: None

- **prompt**: 
  - **Type**: `str`
  - **Description**: The textual prompt for image generation.
  - **Modes**: Input, Property
  - **UI Options**: Placeholder text for user guidance.

- **enhance_prompt**: 
  - **Type**: `bool`
  - **Description**: Flag to enhance the prompt for better image quality.
  - **Default**: `True`

- **output**: 
  - **Type**: `ImageArtifact`
  - **Description**: The generated image artifact.
  - **Modes**: Output

## Outputs

- **ImageArtifact**: The resulting image generated from the provided prompt.


## Important Notes

- **API Key Requirement**: Ensure that the `GT_CLOUD_API_KEY` environment variable is set for authentication with Griptape Cloud services.
- **Default Settings**: The node uses `dall-e-3` as the default model and `hd` as the default quality.

## Common Issues

- **Missing API Key**: If the API key is not defined, a `KeyError` will be raised.
- **Parameter Validation**: Ensure that both `agent` and `driver` parameters are correctly set to avoid validation errors.