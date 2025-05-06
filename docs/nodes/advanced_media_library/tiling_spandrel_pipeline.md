# TilingSpandrelPipeline

!!! warning "You need to perform setup steps to use Hugging Face nodes"

    [This guide](../../how_to/hugging_face_install.md) will walk you through setting up a Hugging Face account, creating an access token, and installing the required models to make this node fully functional.

## What is it?

The TilingSpandrelPipeline node is designed to upscale images using the Spandrel model with a tiling approach. It processes images by dividing them into smaller tiles, applying the model to each tile, and then reconstructing the final upscaled image.

## When would I use it?

Use this node when you need to:

- Upscale images while maintaining quality
- Process large images efficiently by dividing them into tiles
- Utilize advanced models for image enhancement
- Experiment with different tiling strategies for image processing

## How to use it

### Basic Setup

1. Add the TilingSpandrelPipeline node to your workflow
1. Connect an image source to the "input_image" parameter
1. Set the desired model in the "model" parameter
1. Optionally configure additional parameters such as "scale", "tile_size", "tile_overlap", and "tile_strategy"
1. Run the node to upscale the image

### Parameters

- **model**: The Spandrel model to use for image upscaling (default: "skbhadra/ClearRealityV1")
- **input_image**: The image to be upscaled (ImageArtifact)
- **scale**: The factor by which to upscale the image dimensions (default: 2.0)
- **tile_size**: The size of each tile in pixels (default: 1024)
- **tile_overlap**: The overlap between tiles in pixels (default: 64)
- **tile_strategy**: The strategy for processing tiles (default: "linear"). Options include:
    - "linear"
    - "chess"
    - "random"
    - "inward"
    - "outward"
- **output_image**: The upscaled image as an ImageArtifact
- **logs**: Logs of the image upscaling process

### Outputs

- **output_image**: The final upscaled image as an ImageArtifact
- **logs**: A string containing logs of the image upscaling process

## Important Notes

- The node requires a valid Hugging Face API token set as the environment variable `HUGGINGFACE_HUB_ACCESS_TOKEN`
- Only specific model and filename pairs are supported: ("skbhadra/ClearRealityV1", "4x-ClearRealityV1.pth")
- Tiling strategies can affect the processing time and quality of the upscaled image

## Common Issues

- **Missing API Key**: Ensure the Hugging Face API token is set as `HUGGINGFACE_HUB_ACCESS_TOKEN`; instructions for that are in [this guide](../../how_to/hugging_face_install.md)
- **Memory Constraints**: Large tile sizes or high inference steps may require significant memory resources
