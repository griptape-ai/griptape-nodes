# PillowResize

!!! info "You need to perform setup steps to use Hugging Face nodes"

    [This guide](../) will walk you through setting up a Hugging Face account, creating an access token, and installing the required models to make this node fully functional.

## What is it?

The PillowResize node is used to resize images using the Pillow library. It allows you to scale images by a specified factor and choose from various resampling strategies to maintain image quality.

## When would I use it?

Use this node when you need to:

- Resize images to different dimensions
- Scale images up or down while preserving quality
- Apply specific resampling strategies for image resizing

## How to use it

### Basic Setup

1. Add the PillowResize node to your workflow
1. Connect an image source to the "input_image" parameter
1. Set the desired scale factor in the "scale" parameter
1. Choose a resampling strategy from the "resample_strategy" parameter
1. Run the node to resize the image

### Parameters

- **input_image**: The image to be resized (ImageArtifact)
- **scale**: The factor by which to scale the image dimensions (default: 2.0)
- **resample_strategy**: The resampling strategy to use for resizing (default: "bicubic"). Options include:
    - "nearest"
    - "box"
    - "bilinear"
    - "hamming"
    - "bicubic"
    - "lanczos"
- **output_image**: The resized image as an ImageArtifact

### Outputs

- **output_image**: The resized image as an ImageArtifact

## Important Notes

- Ensure the input image is a valid ImageArtifact before processing
- The scale factor must be a positive float value
- Different resampling strategies can affect the quality and processing time of the resized image

## Common Issues

- **Unsupported Resample Strategy**: Ensure the resampling strategy is one of the supported options
- **Invalid Scale Factor**: The scale factor should be a positive number to avoid errors
- **No Image Provided**: Make sure an image is connected to the "input_image" parameter before running the node
