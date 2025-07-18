# ApplyMask

## What is it?

The ApplyMask node applies a mask to an input image to create transparency effects. It takes an image and a mask, then uses a specified channel from the mask as the alpha channel for the final image. You can choose which channel to use (red, green, blue, or alpha) depending on where your mask data is stored. This allows you to selectively make parts of an image transparent based on the mask.

## When would I use it?

Use this node when you want to:

- Apply transparency effects to images using masks
- Create selective transparency for image compositing
- Use masks created by other nodes (DisplayMask, PaintMask, InvertMask) to modify image transparency
- Create cutouts or remove backgrounds from images
- Apply complex transparency effects in image processing workflows
- Control which channel of a mask image to use for transparency

## How to use it

### Basic Setup

1. Add the ApplyMask node to your workflow
1. Connect an image source to the "input_image" input
1. Connect a mask source to the "input_mask" input
1. Select the appropriate channel in the "channel" parameter
1. The masked image will be available at the "output" parameter

### Parameters

- **input_image**: The image to apply the mask to (can be connected from other image nodes)
- **input_mask**: The mask to apply (can be connected from mask nodes like DisplayMask, PaintMask, or InvertMask)
- **channel**: Which channel to use from the mask image:

  - **red**: Use the red channel (default, compatible with PaintMask output)
  - **green**: Use the green channel
  - **blue**: Use the blue channel  
  - **alpha**: Use the alpha channel (when available)

### Outputs

- **output**: The final image with the mask applied (transparency based on the mask)

## Example

A common workflow pattern:

1. Generate or load an image using nodes like GenerateImage or LoadImage
1. Create a mask using nodes like DisplayMask or PaintMask
1. Connect the image to the ApplyMask node's "input_image" parameter
1. Connect the mask to the ApplyMask node's "input_mask" parameter
1. Select the appropriate channel (usually "red" for PaintMask output, "alpha" for RGBA masks)
1. The ApplyMask node will apply the mask to create transparency effects
1. Connect the "output" to DisplayImage to view the final result

## Important Notes

- **Channel Selection**: Choose the channel that contains your mask data:

  - **PaintMask output**: Usually use "red" channel
  - **RGBA masks with alpha data**: Use "alpha" channel
  - **Custom masks**: Try different channels to see which works best
  
- **Mask Processing**: The mask is automatically resized to match the input image dimensions
- **RGBA Output**: The final image is converted to RGBA format to support transparency
- **Real-time Processing**: The node processes immediately when both inputs are available
- **Output Format**: The masked image is saved as a PNG file to preserve transparency

## Common Issues

- **No Output**: Check that both "input_image" and "input_mask" are properly connected
- **Unexpected Transparency**: Remember that white areas in the mask become opaque, black areas become transparent
- **Wrong Channel**: If the mask isn't applying correctly, try a different channel (red, green, blue, or alpha)
- **Mask Size Mismatch**: The mask is automatically resized to match the input image, but this may affect quality

## Technical Details

The node processes the mask and image through several steps:

- **Image Loading**: Loads both the input image and mask from their URLs
- **Channel Extraction**: Extracts the specified channel from the mask image:

  - RGB images: Can extract red, green, or blue channels
  - RGBA images: Can extract red, green, blue, or alpha channels
  - L (grayscale) images: Uses the grayscale channel directly
  - LA images: Can extract alpha or grayscale channels
  
- **Resizing**: Resizes the extracted channel to match the input image dimensions
- **Alpha Application**: Applies the channel as the alpha channel to the input image using `putalpha()`
- **Output Generation**: Saves the result as a new RGBA image artifact

The node handles different mask formats:

- **RGB**: Can extract red, green, or blue channels (alpha falls back to red)
- **RGBA**: Can extract red, green, blue, or alpha channels
- **L**: Uses grayscale channel directly (channel parameter ignored)
- **LA**: Can extract alpha or grayscale channels
- **Other formats**: Raises an error for unsupported modes
