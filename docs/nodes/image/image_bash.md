# ImageBash

## What is it?

The ImageBash node allows you to create composite images by combining multiple images into a single canvas. It's perfect for creating collages, image grids, or combining multiple images into one cohesive composition with customizable canvas sizes and background colors.

## When would I use it?

Use this node when you want to:

- Create image collages or grids
- Combine multiple images into a single composition
- Create image mosaics or patterns
- Build image galleries or portfolios
- Combine related images for comparison
- Create social media image layouts
- Build image-based presentations

## How to use it

### Basic Setup

1. Add the ImageBash node to your workflow
1. Connect multiple image sources to the "input_images" input
1. Set the canvas size and background color
1. The composite image will be available at the "output_image" parameter

### Parameters

#### Canvas Settings

- **canvas_size**: The size of the output canvas

    - **Custom**: Set custom width and height
    - **HD**: 1280x720
    - **Full HD**: 1920x1080
    - **4K**: 3840x2160
    - **Square**: 1024x1024
    - **Instagram Post**: 1080x1080
    - **Instagram Story**: 1080x1920

- **width** (pixels, default: 1920): Custom canvas width (when canvas_size is "Custom")

- **height** (pixels, default: 1080): Custom canvas height (when canvas_size is "Custom")

- **background_color** (hex color, default: #ffffff): Background color for empty areas

#### Image Input

- **input_images**: List of images to combine (can be connected from multiple image sources)

### Outputs

- **output_image**: The composite image with all input images combined

## Example

A typical image bashing workflow:

1. Load multiple images using LoadImage nodes
1. Connect all images to the ImageBash node's "input_images" parameter
1. Set the canvas settings:
    - Select "Full HD" for a 1920x1080 canvas
    - Set background_color to "#f0f0f0" for a light gray background
1. The node will automatically arrange the images on the canvas
1. Connect the "output_image" to DisplayImage to view the result

## Important Notes

- **Automatic Layout**: The node automatically arranges images on the canvas
- **Flexible Canvas**: Choose from preset sizes or set custom dimensions
- **Background Control**: Set any background color for empty areas
- **Multiple Images**: Can handle any number of input images

## Common Issues

- **No Images Showing**: Make sure you've connected images to the "input_images" parameter
- **Images Too Small**: Increase canvas size or check image dimensions
- **Wrong Background**: Adjust the background_color parameter to your preference

## Technical Details

The node performs the following operations:

1. **Canvas Creation**: Creates a new canvas with the specified size and background color
1. **Image Arrangement**: Automatically positions input images on the canvas
1. **Compositing**: Combines all images into a single composite image
1. **Output Generation**: Saves the final composite as a high-quality image

This provides a powerful way to create complex image compositions from multiple sources.
