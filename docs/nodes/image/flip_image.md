# FlipImage

## What is it?

The FlipImage node flips images horizontally, vertically, or in both directions. It's perfect for creating mirror effects, correcting orientation issues, or creating symmetrical compositions from existing images.

## When would I use it?

Use this node when you want to:

- Create mirror effects or reflections
- Correct images that are oriented incorrectly
- Create symmetrical compositions
- Generate variations of existing images
- Flip images for artistic or design purposes
- Create left/right or up/down variations of the same image

## How to use it

### Basic Setup

1. Add the FlipImage node to your workflow
1. Connect an image source to the "input_image" input
1. Choose your flip direction
1. The flipped image will be available at the "output" parameter

### Parameters

#### Flip Settings

- **direction**: The direction to flip the image
    - **horizontal**: Flip left to right (mirror effect)
    - **vertical**: Flip top to bottom (upside down)
    - **both**: Flip both horizontally and vertically (180° rotation)

### Outputs

- **output**: The flipped image
- **was_successful**: Indicates whether the flip operation succeeded
- **result_details**: Detailed information about the flip operation

## Example

A typical flipping workflow:

1. Load an image using LoadImage
1. Connect that image to the FlipImage node's "input_image" parameter
1. Set the flip direction:

    - Select "horizontal" to create a mirror image
    - Select "vertical" to flip upside down
    - Select "both" to rotate 180 degrees
1. Connect the "output" to DisplayImage to view the result

## Important Notes

- **Live Preview**: Changes are applied in real-time as you adjust parameters
- **Format Preservation**: The node preserves the original image format and quality
- **RGBA Support**: The node preserves transparency in RGBA images
- **Success/Failure Tracking**: The node provides detailed status information about the operation

## Common Issues

- **No Output**: Check that your image source is properly connected to the "input_image" parameter
- **Unexpected Results**: Remember that "horizontal" flips left-to-right, "vertical" flips top-to-bottom
- **Both Direction**: "both" applies both horizontal and vertical flips, effectively rotating the image 180 degrees

## Technical Details

The node uses PIL's image operations:

- **Horizontal Flip**: Uses `ImageOps.mirror()` for left-to-right flipping
- **Vertical Flip**: Uses `ImageOps.flip()` for top-to-bottom flipping
- **Both Directions**: Applies both operations sequentially

This provides reliable image flipping capabilities with proper error handling and status reporting.
