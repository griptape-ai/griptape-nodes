# DisplayMask

## What is it?

The DisplayMask node creates a mask from an input image by extracting its alpha channel. A mask is a grayscale image where white areas represent fully opaque regions and black areas represent fully transparent regions. This node is useful for visualizing and working with transparency information in images.

## When would I use it?

Use this node when you want to:

- Extract transparency information from an image as a visible mask
- Create masks for image editing workflows
- Visualize the alpha channel of an image
- Generate masks for use in other image processing nodes
- Debug transparency issues in your image pipeline

## How to use it

### Basic Setup

1. Add the DisplayMask node to your workflow
1. Connect an image source to the "input_image" input
1. The generated mask will be available at the "output_mask" parameter

### Parameters

- **input_image**: The image to create a mask from (can be connected from other image nodes)

### Outputs

- **output_mask**: A grayscale mask image created from the alpha channel of the input image

## Example

A common workflow pattern:

1. Generate or load an image using nodes like GenerateImage or LoadImage
1. Connect that image to the DisplayMask node's "input_image" parameter
1. The DisplayMask node will extract the alpha channel and create a visible mask
1. Connect the "output_mask" to DisplayImage to view the mask, or to other mask processing nodes

## Important Notes

- **Alpha Channel Extraction**: The node extracts the alpha channel from the input image to create the mask
- **Grayscale Output**: The resulting mask is a grayscale image where white represents opaque areas and black represents transparent areas
- **Real-time Processing**: The node processes the image immediately when a connection is made or when the input value changes
- **Output Format**: The mask is saved as a PNG file to preserve quality

## Common Issues

- **No Output**: Check that your image source is properly connected to the "input_image" parameter
- **Solid Black Mask**: This may indicate that the input image has no transparency (fully opaque)
- **Solid White Mask**: This may indicate that the input image is fully transparent

## Technical Details

The node uses the `create_alpha_mask` utility function to:

- Load the input image from its URL
- Extract the alpha channel
- Convert it to a grayscale mask
- Save the result as a new image artifact
