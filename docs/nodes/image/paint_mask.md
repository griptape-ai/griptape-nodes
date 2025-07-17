# PaintMask

## What is it?

The PaintMask node creates an editable mask from an input image and allows you to paint on it to modify the transparency. It automatically generates an initial mask from the image's alpha channel, then provides an interactive painting interface where you can edit the mask by painting on it. The node also applies the mask to the input image to show the final result.

## When would I use it?

Use this node when you want to:

- Create custom masks for image editing and compositing
- Manually refine automatically generated masks
- Paint transparency effects on images
- Create selective transparency for image overlays
- Fine-tune mask boundaries for precise image editing

## How to use it

### Basic Setup

1. Add the PaintMask node to your workflow
1. Connect an image source to the "input_image" input
1. The node will automatically generate an initial mask from the image's alpha channel
1. Use the painting interface in the "output_mask" parameter to edit the mask
1. The final masked image will be available at the "output_image" parameter

### Parameters

- **input_image**: The image to create a mask from (can be connected from other image nodes)

### Outputs

- **output_mask**: An editable mask image that you can paint on to modify transparency
- **output_image**: The final image with the mask applied (transparency based on the mask)

## Example

A common workflow pattern:

1. Generate or load an image using nodes like GenerateImage or LoadImage
1. Connect that image to the PaintMask node's "input_image" parameter
1. The node will create an initial mask from the image's alpha channel
1. Use the painting tools in the "output_mask" parameter to refine the mask
1. The "output_image" will show the result with your painted mask applied
1. Connect the "output_image" to DisplayImage to view the final result

## Important Notes

- **Automatic Mask Generation**: The node automatically creates an initial mask from the input image's alpha channel
- **Interactive Painting**: You can paint directly on the mask using the built-in painting interface
- **Mask Persistence**: The mask is preserved when you change the input image, unless the source image URL changes
- **Red Channel Usage**: The mask uses the red channel of the painted image as the alpha channel for the final result
- **Real-time Updates**: Changes to the mask are immediately reflected in the output image

## Common Issues

- **No Output**: Check that your image source is properly connected to the "input_image" parameter
- **Mask Not Updating**: If you change the input image, the mask may need to be regenerated
- **Painting Not Working**: Make sure you're using the painting interface in the "output_mask" parameter
- **Unexpected Transparency**: Remember that white areas in the mask become opaque, black areas become transparent

## Technical Details

The node handles mask generation and editing through several key processes:

- **Initial Mask Creation**: Extracts the alpha channel from the input image and converts it to a grayscale mask
- **Mask Editing**: Provides an interactive interface for painting on the mask
- **Mask Application**: Uses the red channel of the painted mask as the alpha channel for the final image
- **Persistence**: Tracks whether the mask has been manually edited to determine when to regenerate vs. preserve edits 