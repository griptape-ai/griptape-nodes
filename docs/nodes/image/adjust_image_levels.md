# AdjustImageLevels

## What is it?

The AdjustImageLevels node provides professional-level image adjustment capabilities similar to Photoshop's levels tool. It allows you to control input levels (shadows, midtones, highlights) and output levels, giving you precise control over the tonal range and contrast of your images.

## When would I use it?

Use this node when you want to:

- Fine-tune the tonal range of your images
- Adjust shadows and highlights independently
- Control midtone brightness with gamma correction
- Create high-contrast or low-contrast effects
- Fix exposure issues in images
- Match the tonal characteristics of multiple images
- Prepare images for specific output requirements

## How to use it

### Basic Setup

1. Add the AdjustImageLevels node to your workflow
1. Connect an image source to the "input_image" input
1. Adjust the input and output level sliders
1. The processed image will be available at the "output" parameter

### Parameters

#### Input Levels

- **shadows** (0-255, default: 0): Input shadows level

    - Pixels below this value will be mapped to output shadows
    - Higher values clip more shadow detail

- **midtones** (0.1-10.0, default: 1.0): Midtones adjustment (gamma)

    - Values < 1.0 brighten midtones
    - Values > 1.0 darken midtones
    - 1.0 = no change

- **highlights** (0-255, default: 255): Input highlights level

    - Pixels above this value will be mapped to output highlights
    - Lower values clip more highlight detail

#### Output Levels

- **output_shadows** (0-255, default: 0): Output shadows level

    - Input shadows will be mapped to this value
    - Higher values brighten the overall image

- **output_highlights** (0-255, default: 255): Output highlights level

    - Input highlights will be mapped to this value
    - Lower values darken the overall image

### Outputs

- **output**: The adjusted image with your levels settings applied

## Example

A typical levels adjustment workflow:

1. Load an image using LoadImage
1. Connect that image to the AdjustImageLevels node's "input_image" parameter
1. Adjust the levels to improve the image:
    - Set shadows to 20 to preserve more shadow detail
    - Set midtones to 0.8 to brighten midtones
    - Set highlights to 240 to preserve more highlight detail
    - Set output_shadows to 10 to slightly brighten shadows
    - Set output_highlights to 245 to slightly darken highlights
1. Connect the "output" to DisplayImage to view the result

## Important Notes

- **Live Preview**: Changes are applied in real-time as you move the sliders
- **RGBA Support**: The node preserves transparency in RGBA images
- **Professional Quality**: Uses lookup tables for precise level adjustments
- **Validation**: The node ensures shadows < highlights for proper operation

## Common Issues

- **No Changes Visible**: Make sure you're adjusting the sliders away from their default values
- **Over-processed Look**: Be careful with extreme values - subtle adjustments often work best
- **Clipping**: Setting shadows too high or highlights too low can cause detail loss

## Technical Details

The node applies a three-step process:

1. **Input Levels**: Clips and maps the input range based on shadows and highlights
1. **Gamma Correction**: Applies midtone adjustment using power-law transformation
1. **Output Levels**: Maps the processed values to the output range

This provides the same functionality as professional photo editing software's levels adjustment tool.
