# DisplayChannel

## What is it?

The DisplayChannel node creates a mask from an input image by extracting a specific color channel (red, green, blue, or alpha). This node is similar to DisplayMask but defaults to extracting the red channel instead of the alpha channel. A mask is a grayscale image where white areas represent high values and black areas represent low values for the selected channel.

## When would I use it?

Use this node when you want to:

- Extract specific color channels (red, green, blue) as an image
- Analyze the intensity of individual color channels in an image
- Create masks for image editing workflows based on color information
- Visualize how different color channels contribute to an image
- Generate color-based masks for use in other image processing nodes
- Debug color channel issues in your image pipeline
- Focus on red channel analysis (since it's the default)

## How to use it

### Basic Setup

1. Add the DisplayChannel node to your workflow
1. Connect an image source to the "input_image" input
1. Select the desired channel from the "channel" dropdown (defaults to "red")
1. The generated channel image will be available at the "output" parameter

### Parameters

- **input_image**: The image to create a mask from (can be connected from other image nodes)
- **channel**: The channel to extract as a mask (red, green, blue, or alpha) - defaults to "red"

### Outputs

- **output**: A grayscale mask image created from the selected channel of the input image

## Example

A common workflow pattern:

1. Generate or load an image using nodes like GenerateImage or LoadImage
1. Connect that image to the DisplayChannel node's "input_image" parameter
1. The node will default to extracting the red channel, or you can select a different channel
1. The DisplayChannel node will extract the selected channel and create a visible mask
1. Connect the "output" to DisplayImage to view the mask, or to other mask processing nodes

## Channel Options

- **red**: Extracts the red color channel (default) - useful for isolating red elements in an image
- **green**: Extracts the green color channel - useful for isolating green elements in an image
- **blue**: Extracts the blue color channel - useful for isolating blue elements in an image
- **alpha**: Extracts the transparency channel - useful for seeing which parts of an image are transparent

## Important Notes

- **Default Channel**: Unlike DisplayMask, this node defaults to the "red" channel instead of "alpha"
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

## Difference from DisplayMask

The main difference between DisplayChannel and DisplayMask is the default channel selection:

- **DisplayChannel**: Defaults to "red" channel
- **DisplayMask**: Defaults to "alpha" channel

This makes DisplayChannel more suitable for color analysis workflows, while DisplayMask is better for transparency-based workflows.
