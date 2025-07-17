# ApplyMask

## What is it?

The ApplyMask node applies a mask to an input image to create transparency effects. It takes an image and a mask, then uses the red channel of the mask as the alpha channel for the final image. This allows you to selectively make parts of an image transparent based on the mask.

## When would I use it?

Use this node when you want to:

- Apply transparency effects to images using masks
- Create selective transparency for image compositing
- Use masks created by other nodes (DisplayMask, PaintMask, InvertMask) to modify image transparency
- Create cutouts or remove backgrounds from images
- Apply complex transparency effects in image processing workflows

## How to use it

### Basic Setup

1. Add the ApplyMask node to your workflow
1. Connect an image source to the "input_image" input
1. Connect a mask source to the "input_mask" input
1. The masked image will be available at the "output" parameter

### Parameters

- **input_image**: The image to apply the mask to (can be connected from other image nodes)
- **input_mask**: The mask to apply (can be connected from mask nodes like DisplayMask, PaintMask, or InvertMask)

### Outputs

- **output**: The final image with the mask applied (transparency based on the mask)

## Example

A common workflow pattern:

1. Generate or load an image using nodes like GenerateImage or LoadImage
1. Create a mask using nodes like DisplayMask or PaintMask
1. Connect the image to the ApplyMask node's "input_image" parameter
1. Connect the mask to the ApplyMask node's "input_mask" parameter
1. The ApplyMask node will apply the mask to create transparency effects
1. Connect the "output" to DisplayImage to view the final result

## Important Notes

- **Red Channel Usage**: The node uses the red channel of the mask as the alpha channel for the final image
- **Mask Processing**: The mask is automatically resized to match the input image dimensions
- **RGBA Output**: The final image is converted to RGBA format to support transparency
- **Real-time Processing**: The node processes immediately when both inputs are available
- **Output Format**: The masked image is saved as a PNG file to preserve transparency

## Common Issues

- **No Output**: Check that both "input_image" and "input_mask" are properly connected
- **Unexpected Transparency**: Remember that white areas in the mask become opaque, black areas become transparent
- **Mask Size Mismatch**: The mask is automatically resized to match the input image, but this may affect quality
- **Color Mask**: The node uses only the red channel of the mask, so color information in the mask is ignored

## Technical Details

The node processes the mask and image through several steps:

- **Image Loading**: Loads both the input image and mask from their URLs
- **Channel Extraction**: Extracts the red channel from the mask to use as the alpha channel
- **Resizing**: Resizes the alpha channel to match the input image dimensions
- **Alpha Application**: Applies the alpha channel to the input image using `putalpha()`
- **Output Generation**: Saves the result as a new RGBA image artifact

The node handles different mask formats:

- **RGB**: Uses the red channel directly
- **RGBA**: Uses the red channel (ignores the original alpha)
- **Other formats**: Converts to RGB first, then uses the red channel
