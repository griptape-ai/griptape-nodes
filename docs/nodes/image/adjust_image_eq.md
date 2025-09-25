# AdjustImageEQ

## What is it?

The AdjustImageEQ node allows you to fine-tune your images with precise controls for brightness, contrast, saturation, and gamma correction. It's like having a professional photo editing tool built into your workflow, giving you complete control over the visual appearance of your images.

## When would I use it?

Use this node when you want to:

- Enhance image brightness and contrast for better visibility
- Adjust color saturation to make colors more vibrant or muted
- Apply gamma correction to fix exposure issues
- Fine-tune images before passing them to other processing nodes
- Create consistent lighting across multiple images
- Prepare images for specific output requirements

## How to use it

### Basic Setup

1. Add the AdjustImageEQ node to your workflow
1. Connect an image source to the "input_image" input
1. Adjust the sliders to fine-tune your image
1. The processed image will be available at the "output" parameter

### Parameters

#### Adjustment Settings

- **brightness** (0.0-3.0, default: 1.0): Controls overall image brightness

    - Values < 1.0 make the image darker
    - Values > 1.0 make the image brighter
    - 1.0 = no change

- **contrast** (0.0-3.0, default: 1.0): Controls the difference between light and dark areas

    - Values < 1.0 reduce contrast (more gray)
    - Values > 1.0 increase contrast (more dramatic)
    - 1.0 = no change

- **saturation** (0.0-3.0, default: 1.0): Controls color intensity

    - Values < 1.0 reduce saturation (more grayscale)
    - Values > 1.0 increase saturation (more vibrant colors)
    - 1.0 = no change

- **gamma** (0.1-10.0, default: 1.0): Controls midtone brightness

    - Values < 1.0 brighten midtones
    - Values > 1.0 darken midtones
    - 1.0 = no change

### Outputs

- **output**: The adjusted image with your EQ settings applied

## Example

A typical image enhancement workflow:

1. Load or generate an image using LoadImage or GenerateImage
1. Connect that image to the AdjustImageEQ node's "input_image" parameter
1. Adjust the sliders to achieve your desired look:
    - Increase brightness to 1.2 for a brighter image
    - Increase contrast to 1.1 for more dramatic shadows
    - Increase saturation to 1.3 for more vibrant colors
    - Adjust gamma to 0.9 to brighten midtones
1. Connect the "output" to DisplayImage to view the result

## Important Notes

- **Live Preview**: Changes are applied in real-time as you move the sliders
- **RGBA Support**: The node preserves transparency in RGBA images
- **High Quality**: Uses PIL's ImageEnhance for professional-quality adjustments
- **Non-destructive**: Original image data is preserved in the workflow

## Common Issues

- **No Changes Visible**: Make sure you're moving the sliders away from their default values (1.0)
- **Over-processed Look**: Be careful with extreme values - subtle adjustments often work best
- **Color Shifts**: Gamma adjustments can affect color balance, so monitor the overall result

## Technical Details

The node uses PIL's ImageEnhance module for high-quality image adjustments:

- **Brightness**: Multiplies pixel values by the brightness factor
- **Contrast**: Applies contrast enhancement using PIL's contrast algorithm
- **Saturation**: Uses PIL's color enhancement for saturation control
- **Gamma**: Applies gamma correction using lookup tables for precise control
