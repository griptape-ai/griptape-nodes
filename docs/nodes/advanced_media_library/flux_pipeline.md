# FluxPipeline

!!! warning "You need to perform setup steps to use Hugging Face nodes"

    [This guide](../../how_to/hugging_face_install.md) will walk you through setting up a Hugging Face account, creating an access token, and installing the required models to make this node fully functional.

## What is it?

The FluxPipeline node is designed to generate images from text prompts using the FLUX.1 model. It integrates with Hugging Face's diffusers library to create high-quality images based on specified prompts and parameters.

## When would I use it?

Use this node when you need to:

- Generate images from textual descriptions
- Leverage advanced image generation models for creative projects
- Experiment with different image styles and configurations using the FLUX.1 model

## How to use it

### Basic Setup

1. Add the FluxPipeline node to your workflow
1. Set the desired model in the "model" parameter
1. Provide a text prompt in the "prompt" parameter
1. Optionally configure additional parameters such as "width", "height", and "guidance_scale"
1. Run the node to generate an image

### Parameters

- **model**: The FLUX.1 model to use for image generation (default: "black-forest-labs/FLUX.1-schnell")
- **prompt**: The primary text prompt for image generation
- **prompt_2**: An optional secondary prompt (defaults to the primary prompt if not provided)
- **negative_prompt**: An optional negative prompt to influence image generation
- **negative_prompt_2**: An optional secondary negative prompt (defaults to the primary negative prompt if not provided)
- **true_cfg_scale**: A float value to adjust the configuration scale (default: 1.0)
- **width**: The width of the generated image in pixels (default: 1024)
- **height**: The height of the generated image in pixels (default: 1024)
- **num_inference_steps**: The number of inference steps for image generation (default: 4)
- **guidance_scale**: A float value to adjust the guidance scale (default: 3.5)
- **seed**: An optional integer seed for random number generation (default: random)
- **output_image**: The generated image as an ImageArtifact
- **logs**: Logs of the image generation process

### Outputs

- **output_image**: The final generated image as an ImageArtifact
- **logs**: A string containing logs of the image generation process

## Important Note

- Only specific FLUX.1 models are currently supported: "black-forest-labs/FLUX.1-schnell" and "black-forest-labs/FLUX.1-dev"

## Common Issues

- **Missing API Key**: Ensure the Hugging Face API token is set as `HUGGINGFACE_HUB_ACCESS_TOKEN`; instructions for that are in [this guide](../../how_to/hugging_face_install.md)
- **Memory Constraints**: Large image dimensions or high inference steps may require significant memory resources
