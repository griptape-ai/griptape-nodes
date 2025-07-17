# InvertImage

## What is it?

The InvertImage node creates a negative version of an input image by inverting all the color values. It's like creating a photographic negative - dark areas become light, light areas become dark, and colors are inverted to their complementary colors.

## When would I use it?

Use this node when you want to:

- Create artistic effects by inverting image colors
- Generate negative versions of images for creative purposes
- Create high-contrast effects for image processing workflows
- Experiment with different visual styles in your image generation pipelines
- Create complementary color schemes from existing images

## How to use it

### Basic Setup

1. Add the InvertImage node to your workflow
1. Connect an image source to the "input_image" input
1. The inverted image will be available at the "output" parameter

### Parameters

- **input_image**: The image to invert (can be connected from other image nodes)

### Outputs

- **output**: The inverted (negative) version of the input image

## Example

A common workflow pattern:

1. Generate or load an image using nodes like GenerateImage or LoadImage
1. Connect that image to the InvertImage node's "input_image" parameter
1. The InvertImage node will create a negative version of the image
1. Connect the "output" to DisplayImage to view the result, or to other processing nodes

## Important Notes

- **RGBA Images**: For images with transparency (RGBA), the node inverts the RGB color channels while preserving the original alpha channel
- **Other Formats**: Images in other formats are converted to RGB before inversion
- **Real-time Processing**: The node processes the image immediately when a connection is made or when the input value changes
- **Output Format**: The inverted image is saved as a PNG file to preserve quality

## Common Issues

- **No Output**: Check that your image source is properly connected to the "input_image" parameter
- **Unexpected Results**: Remember that inversion creates a negative - dark areas become light and vice versa
- **Transparency Issues**: If you need to preserve specific transparency effects, the node will maintain the original alpha channel for RGBA images

## Technical Details

The node handles different image modes intelligently:

- **RGBA**: Inverts RGB channels, preserves alpha channel
- **RGB**: Direct inversion of all color values
- **Other modes**: Converts to RGB first, then inverts
