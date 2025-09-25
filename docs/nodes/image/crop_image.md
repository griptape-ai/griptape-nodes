# CropImage

## What is it?

The CropImage node provides precise control over image cropping, zooming, and rotation. It allows you to select specific areas of an image, apply zoom effects, and rotate images to achieve the perfect composition for your workflow.

## When would I use it?

Use this node when you want to:

- Crop images to specific dimensions or aspect ratios
- Focus on particular areas of an image
- Apply zoom effects to magnify details
- Rotate images to correct orientation
- Create consistent image sizes across your workflow
- Remove unwanted areas from images
- Prepare images for specific output requirements

## How to use it

### Basic Setup

1. Add the CropImage node to your workflow
1. Connect an image source to the "input_image" input
1. Set the crop coordinates and dimensions
1. Optionally adjust zoom and rotation
1. The processed image will be available at the "output" parameter

### Parameters

#### Crop Settings

- **left** (0+, default: 0): Left edge of the crop area in pixels
- **top** (0+, default: 0): Top edge of the crop area in pixels
- **width** (1+, default: 100): Width of the crop area in pixels
- **height** (1+, default: 100): Height of the crop area in pixels

#### Transform Settings

- **zoom** (1.0+, default: 1.0): Zoom factor for the crop area

    - 1.0 = no zoom
    - Values > 1.0 zoom in (magnify)
    - Values < 1.0 zoom out (shrink)

- **rotate** (degrees, default: 0): Rotation angle in degrees

    - Positive values rotate clockwise
    - Negative values rotate counter-clockwise

### Outputs

- **output**: The cropped and transformed image

## Example

A typical cropping workflow:

1. Load an image using LoadImage
1. Connect that image to the CropImage node's "input_image" parameter
1. Set the crop area:
    - Set left to 100 to start cropping 100 pixels from the left
    - Set top to 50 to start cropping 50 pixels from the top
    - Set width to 400 to crop 400 pixels wide
    - Set height to 300 to crop 300 pixels tall
1. Optionally add effects:
    - Set zoom to 1.2 to magnify the cropped area by 20%
    - Set rotate to 15 to rotate the image 15 degrees clockwise
1. Connect the "output" to DisplayImage to view the result

## Important Notes

- **Live Preview**: Changes are applied in real-time as you adjust parameters
- **Boundary Checking**: The node ensures crop areas stay within image bounds
- **High Quality**: Uses high-quality resampling for zoom and rotation
- **RGBA Support**: The node preserves transparency in RGBA images

## Common Issues

- **Empty Crop Area**: Make sure width and height are greater than 0
- **Crop Outside Image**: Ensure left + width and top + height don't exceed image dimensions
- **Unexpected Results**: Check that your crop coordinates are within the image bounds

## Technical Details

The node performs the following operations:

1. **Crop**: Extracts the specified rectangular area from the image
1. **Zoom**: Scales the cropped area using high-quality resampling
1. **Rotate**: Rotates the image around its center point
1. **Boundary Management**: Ensures all operations stay within valid image bounds

This provides professional-quality image cropping and transformation capabilities.
