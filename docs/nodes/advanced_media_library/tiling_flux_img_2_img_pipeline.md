# TilingFluxImg2ImgPipeline

!!! warning "You need to perform setup steps to use Hugging Face nodes"

    [This guide](../../how_to/hugging_face_install.md) will walk you through setting up a Hugging Face account, creating an access token, and installing the required models to make this node fully functional.

## What is it?

The TilingFluxImg2ImgPipeline node is designed to transform images using the FLUX.1 model with a tiling approach. It allows for image-to-image transformations based on text prompts, utilizing Hugging Face's diffusers library to apply changes across image tiles for efficient processing.

## When would I use it?

Use this node when you need to:

- Apply image-to-image transformations using text prompts
- Process large images by dividing them into smaller tiles
- Utilize advanced models for creative image manipulation
- Experiment with different tiling strategies for image processing

## How to use it

### Basic Setup

1. Add the TilingFluxImg2ImgPipeline node to your workflow
1. Connect an image source to the "input_image" parameter
1. Set the desired model in the "model" parameter
1. Provide a text prompt in the "prompt" parameter
1. Optionally configure additional parameters such as "tile_size", "tile_overlap", and "tile_strategy"
1. Run the node to transform the image

### Parameters

- **model**: The FLUX.1 model to use for image transformation (default: "black-forest-labs/FLUX.1-schnell")
- **input_image**: The image to be transformed (ImageArtifact)
- **prompt**: The primary text prompt for image transformation
- **prompt_2**: An optional secondary prompt (defaults to the primary prompt if not provided)
- **negative_prompt**: An optional negative prompt to influence image transformation
- **negative_prompt_2**: An optional secondary negative prompt (defaults to the primary negative prompt if not provided)
- **true_cfg_scale**: A float value to adjust the configuration scale (default: 1.0)
- **num_inference_steps**: The number of inference steps for image transformation (default: 16)
- **strength**: A float value indicating the transformation strength (default: 0.3)
- **guidance_scale**: A float value to adjust the guidance scale (default: 3.5)
- **seed**: An optional integer seed for random number generation (default: random)
- **scale**: A float value for scaling the image (default: 1.0)
- **tile_size**: The size of each tile in pixels (default: 1024)
- **tile_overlap**: The overlap between tiles in pixels (default: 64)
- **tile_strategy**: The strategy for processing tiles (default: "linear"). Options include:
    - "linear"
    - "chess"
    - "random"
    - "inward"
    - "outward"
- **output_image**: The transformed image as an ImageArtifact
- **logs**: Logs of the image transformation process

### Outputs

- **output_image**: The final transformed image as an ImageArtifact
- **logs**: A string containing logs of the image transformation process

## Important Notes

- The node requires a valid Hugging Face API token set as the environment variable `HUGGINGFACE_HUB_ACCESS_TOKEN`
- Only specific FLUX.1 models are supported: "black-forest-labs/FLUX.1-schnell" and "black-forest-labs/FLUX.1-dev"
- Tiling strategies can affect the processing time and quality of the transformed image

## Common Issues

- **Missing API Key**: Ensure the Hugging Face API token is set as `HUGGINGFACE_HUB_ACCESS_TOKEN`; instructions for that are in [this guide](../../how_to/hugging_face_install.md)
- **Memory Constraints**: Large tile sizes or high inference steps may require significant memory resources
