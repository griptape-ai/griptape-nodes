# ExtendCanvas

## What is it?

The ExtendCanvas node allows you to extend the canvas around an image to fit target aspect ratios or custom dimensions. It's perfect for adding padding, creating specific aspect ratios, or preparing images for different output formats without cropping the original content.

## When would I use it?

Use this node when you want to:

- Add padding or margins around images
- Create specific aspect ratios (16:9, 4:3, square, etc.)
- Prepare images for different social media formats
- Add space for text overlays or graphics
- Create consistent image dimensions across a workflow
- Prepare images for print layouts
- Add borders or frames around images

## How to use it

### Basic Setup

1. Add the ExtendCanvas node to your workflow
1. Connect an image source to the "input_image" input
1. Set the target aspect ratio or custom dimensions
1. The extended image will be available at the "output" parameter

### Parameters

#### Canvas Settings

- **target_aspect_ratio**: The desired aspect ratio for the output

    - **16:9**: Widescreen format
    - **4:3**: Standard format
    - **1:1**: Square format
    - **3:2**: Photo format
    - **21:9**: Ultra-wide format
    - **Custom**: Set custom dimensions

- **custom_width** (pixels): Custom width when using "Custom" aspect ratio

- **custom_height** (pixels): Custom height when using "Custom" aspect ratio

#### Extension Settings

- **extension_method**: How to extend the canvas

    - **center**: Center the original image on the new canvas
    - **top_left**: Position the original image at the top-left
    - **top_right**: Position the original image at the top-right
    - **bottom_left**: Position the original image at the bottom-left
    - **bottom_right**: Position the original image at the bottom-right

- **background_color** (hex color, default: #ffffff): Color for the extended areas

- **background_opacity** (0.0-1.0, default: 1.0): Opacity of the background color

### Outputs

- **output**: The image with extended canvas

## Example

A typical canvas extension workflow:

1. Load an image using LoadImage
1. Connect that image to the ExtendCanvas node's "input_image" parameter
1. Set the canvas settings:
    - Select "16:9" target_aspect_ratio for widescreen format
    - Select "center" extension_method to center the image
    - Set background_color to "#000000" for a black background
1. Connect the "output" to DisplayImage to view the result

## Important Notes

- **Non-destructive**: The original image content is never cropped or modified
- **Flexible Positioning**: Choose where to position the original image on the new canvas
- **Aspect Ratio Control**: Create any aspect ratio or use preset formats
- **RGBA Support**: The node preserves transparency in RGBA images

## Common Issues

- **Image Not Centered**: Check the extension_method setting
- **Wrong Aspect Ratio**: Verify your target_aspect_ratio selection
- **Background Not Visible**: Make sure background_opacity is greater than 0

## Technical Details

The node performs the following operations:

1. **Canvas Creation**: Creates a new canvas with the target dimensions
1. **Background Fill**: Fills the canvas with the specified background color
1. **Image Positioning**: Places the original image at the specified position
1. **Output Generation**: Saves the final extended image

This provides a powerful way to prepare images for specific output requirements without losing any original content.
