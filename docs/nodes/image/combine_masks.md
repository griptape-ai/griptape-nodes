# CombineMasks

## What is it?

The CombineMasks node merges a list of mask images into a single consolidated mask by taking the **maximum value per pixel** (a union operation).

This is useful when a segmentation node produces multiple masks and you want one mask you can apply downstream.

## When would I use it?

Use this node when you want to:

- Combine multiple segmentation masks into one mask
- Create a single “subject mask” from many detected objects
- Simplify workflows that expect one mask input

## How to use it

### Basic Setup

1. Add the CombineMasks node to your workflow
1. Provide one or more masks to the `masks` input (as a list)
1. Use the `output_mask` output as the consolidated mask

### Parameters

- **masks**: A list of mask images to combine

### Outputs

- **output_mask**: The consolidated mask (PNG)

## Important Notes

- **Union logic**: For each pixel, the output mask uses the maximum value across all input masks.
- **Size requirement**: All input masks must be the **same dimensions**. If sizes differ, the node will fail validation with a clear error.
- **Alpha handling**: If an input mask is RGBA/LA, the node uses the **alpha channel** as the mask; otherwise it converts the image to grayscale.
