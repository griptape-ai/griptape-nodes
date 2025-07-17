# InvertMask

## What is it?

The InvertMask node creates an inverted version of an input mask. It flips the transparency values - areas that were opaque become transparent, and areas that were transparent become opaque. This is useful for creating complementary masks or switching between positive and negative selections.

## When would I use it?

Use this node when you want to:

- Create the opposite of an existing mask
- Switch between positive and negative selections
- Invert transparency effects
- Create complementary masks for image compositing
- Reverse the effect of a mask in your workflow

## How to use it

### Basic Setup

1. Add the InvertMask node to your workflow
1. Connect a mask source to the "input_mask" input
1. The inverted mask will be available at the "output_mask" parameter

### Parameters

- **input_mask**: The mask to invert (can be connected from other mask nodes like DisplayMask or PaintMask)

### Outputs

- **output_mask**: The inverted version of the input mask

## Example

A common workflow pattern:

1. Create a mask using nodes like DisplayMask or PaintMask
1. Connect that mask to the InvertMask node's "input_mask" parameter
1. The InvertMask node will create an inverted version of the mask
1. Connect the "output_mask" to DisplayImage to view the inverted mask, or to other mask processing nodes

## Important Notes

- **Inversion Logic**: White areas in the input mask become black in the output, and black areas become white
- **Alpha Channel Handling**: For RGBA images, the node inverts the alpha channel specifically
- **Grayscale Conversion**: Non-grayscale images are converted to grayscale before inversion
- **Real-time Processing**: The node processes the mask immediately when a connection is made or when the input value changes
- **Output Format**: The inverted mask is saved as a PNG file to preserve quality

## Common Issues

- **No Output**: Check that your mask source is properly connected to the "input_mask" parameter
- **Unexpected Results**: Remember that inversion flips the mask values - what was opaque becomes transparent
- **Color Images**: If you input a color image, it will be converted to grayscale before inversion

## Technical Details

The node handles different image modes intelligently:

- **RGBA**: Inverts the alpha channel while preserving RGB channels
- **Grayscale (L)**: Direct inversion of grayscale values
- **Other modes**: Converts to grayscale first, then inverts

The inversion is performed using the formula: `255 - original_value`, which flips the brightness values.
