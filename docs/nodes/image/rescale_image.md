# RescaleImage

## What is it?

The RescaleImage node allows you to resize images with precise control over dimensions, scaling methods, and quality. It supports both pixel-based and percentage-based scaling, making it perfect for preparing images for specific output requirements or creating different sizes from a single source.

## When would I use it?

Use this node when you want to:

- Resize images to specific dimensions
- Scale images by percentage
- Prepare images for different output formats
- Create thumbnails or preview images
- Optimize images for web or print
- Batch resize multiple images
- Maintain aspect ratios while scaling

## How to use it

### Basic Setup

1. Add the RescaleImage node to your workflow
1. Connect an image source to the "input_image" input
1. Choose your resize mode and set the target size
1. The resized image will be available at the "output" parameter

### Parameters

#### Resize Settings

- **resize_mode**: The method for determining the new size

    - **percentage**: Scale by percentage (e.g., 50% = half size)
    - **pixels**: Set exact pixel dimensions

- **target_size** (pixels, default: 512): Target size when using pixel mode

    - For width-based scaling: sets the width, height scales proportionally
    - For height-based scaling: sets the height, width scales proportionally

- **percentage_scale** (1-1000, default: 100): Scale percentage when using percentage mode

    - 50 = half size
    - 100 = original size
    - 200 = double size

#### Quality Settings

- **resample_filter**: The algorithm used for resampling
    - **lanczos**: High quality, slower (recommended for most cases)
    - **bicubic**: Good quality, medium speed
    - **bilinear**: Lower quality, faster
    - **nearest**: Pixelated, fastest

### Outputs

- **output**: The resized image

## Example

A typical rescaling workflow:

1. Load an image using LoadImage
1. Connect that image to the RescaleImage node's "input_image" parameter
1. Set the resize settings:
    - Select "percentage" resize_mode
    - Set percentage_scale to 50 to create a half-size version
    - Select "lanczos" resample_filter for high quality
1. Connect the "output" to DisplayImage to view the result

## Important Notes

- **Live Preview**: Changes are applied in real-time as you adjust parameters
- **Aspect Ratio**: The node maintains the original aspect ratio
- **High Quality**: Lanczos resampling provides the best quality for most use cases
- **RGBA Support**: The node preserves transparency in RGBA images

## Common Issues

- **Image Too Small**: Increase the percentage_scale or target_size
- **Poor Quality**: Use "lanczos" resample_filter for better quality
- **Wrong Dimensions**: Check that your resize_mode and target settings are correct

## Technical Details

The node uses PIL's resampling algorithms:

- **Lanczos**: Uses Lanczos kernel for high-quality resampling
- **Bicubic**: Uses bicubic interpolation for good quality
- **Bilinear**: Uses bilinear interpolation for faster processing
- **Nearest**: Uses nearest neighbor for pixelated results

This provides professional-quality image resizing capabilities suitable for any workflow.
