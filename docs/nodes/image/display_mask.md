# DisplayMask

## What is it?

The DisplayMask node creates a mask from an input image by extracting a specific channel (red, green, blue, or alpha). A mask is a grayscale image where white areas represent fully opaque regions and black areas represent fully transparent regions. This node is useful for visualizing and working with different color channels in images.

## When would I use it?

Use this node when you want to:

- Extract transparency information from an image as a visible mask
- Extract specific color channels (red, green, blue) as masks
- Create masks for image editing workflows
- Visualize different channels of an image
- Generate masks for use in other image processing nodes
- Debug transparency or color channel issues in your image pipeline

## How to use it

### Basic Setup

1. Add the DisplayMask node to your workflow
1. Connect an image source to the "input_image" input
1. Select the desired channel from the "channel" dropdown
1. The generated mask will be available at the "output_mask" parameter

### Parameters

- **input_image**: The image to create a mask from (can be connected from other image nodes)
- **channel**: The channel to extract as a mask (red, green, blue, or alpha)

### Outputs

- **output_mask**: A grayscale mask image created from the selected channel of the input image

## Example

A common workflow pattern:

1. Generate or load an image using nodes like GenerateImage or LoadImage
1. Connect that image to the DisplayMask node's "input_image" parameter
1. Select the desired channel (e.g., "alpha" for transparency, "red" for red channel)
1. The DisplayMask node will extract the selected channel and create a visible mask
1. Connect the "output_mask" to DisplayImage to view the mask, or to other mask processing nodes

## Channel Options

- **alpha**: Extracts the transparency channel (default) - useful for seeing which parts of an image are transparent
- **red**: Extracts the red color channel - useful for isolating red elements in an image
- **green**: Extracts the green color channel - useful for isolating green elements in an image
- **blue**: Extracts the blue color channel - useful for isolating blue elements in an image

## Important Notes

- **Channel Extraction**: The node extracts the specified channel from the input image to create the mask
- **Grayscale Output**: The resulting mask is a grayscale image where white represents high values and black represents low values for the selected channel
- **Real-time Processing**: The node processes the image immediately when a connection is made or when the input value or channel selection changes
- **Output Format**: The mask is saved as a PNG file to preserve quality
- **Image Mode Support**: Supports RGB, RGBA, grayscale (L), and grayscale+alpha (LA) image modes

## Common Issues

- **No Output**: Check that your image source is properly connected to the "input_image" parameter
- **Solid Black Mask**: This may indicate that the selected channel has no variation or low values
- **Solid White Mask**: This may indicate that the selected channel has high values throughout
- **Unsupported Mode Error**: The image format may not support the selected channel (e.g., alpha channel in RGB images)

## Technical Details

The node uses channel extraction logic to:

- Load the input image from its URL
- Extract the specified channel (red, green, blue, or alpha)
- Convert it to a grayscale mask
- Save the result as a new image artifact

For RGB images, alpha channel selection will fallback to the red channel since RGB doesn't have an alpha channel.
