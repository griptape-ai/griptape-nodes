# ImageBlendCompositor

## What is it?

The ImageBlendCompositor node allows you to blend two images together using various blend modes, similar to layers in photo editing software. It provides precise control over how images are combined, including positioning, opacity, and advanced compositing options.

## When would I use it?

Use this node when you want to:

- Combine two images using different blend modes
- Create composite images with multiple layers
- Apply creative blending effects
- Overlay images with precise positioning
- Create double exposure effects
- Blend textures or patterns onto images
- Create artistic compositions

## How to use it

### Basic Setup

1. Add the ImageBlendCompositor node to your workflow
1. Connect two image sources to the "input_image" and "blend_image" inputs
1. Select a blend mode and adjust opacity
1. The composited image will be available at the "output" parameter

### Parameters

#### Image Inputs

- **input_image**: The base image (background layer)
- **blend_image**: The image to blend on top (foreground layer)

#### Blend Settings

- **blend_mode**: The blending method to use

    - **normal**: Standard alpha blending
    - **multiply**: Darkens the base image
    - **screen**: Lightens the base image
    - **overlay**: Combines multiply and screen
    - **soft_light**: Gentle light/dark effect
    - **hard_light**: Strong light/dark effect
    - **color_dodge**: Brightens base image
    - **color_burn**: Darkens base image
    - **darken**: Keeps darker pixels
    - **lighten**: Keeps lighter pixels
    - **difference**: Subtracts colors
    - **exclusion**: Similar to difference but softer

- **opacity** (0.0-1.0, default: 1.0): Controls the strength of the blend

    - 0.0 = completely transparent (no blend)
    - 1.0 = completely opaque (full blend)

#### Positioning

- **x_offset** (pixels, default: 0): Horizontal position of the blend image
- **y_offset** (pixels, default: 0): Vertical position of the blend image

#### Advanced Options

- **resize_blend_to_fit** (boolean, default: false): Resize blend image to fit base image
- **preserve_alpha** (boolean, default: true): Preserve transparency in the result
- **invert_blend** (boolean, default: false): Invert the blend image before blending

### Outputs

- **output**: The composited image with both images blended together

## Example

A typical blending workflow:

1. Load two images using LoadImage nodes
1. Connect the first image to "input_image" (background)
1. Connect the second image to "blend_image" (foreground)
1. Adjust the blend settings:
    - Select "multiply" blend mode for a darkening effect
    - Set opacity to 0.7 for a subtle blend
    - Set x_offset to 50 to shift the blend image 50 pixels right
    - Set y_offset to 30 to shift the blend image 30 pixels down
1. Connect the "output" to DisplayImage to view the result

## Important Notes

- **Live Preview**: Changes are applied in real-time as you adjust parameters
- **Image Sizes**: The blend image can be positioned outside the base image bounds
- **RGBA Support**: The node preserves transparency in RGBA images
- **High Quality**: Uses professional-grade blending algorithms

## Common Issues

- **No Blend Visible**: Make sure opacity is greater than 0 and blend_mode is not "normal" with full opacity
- **Blend Image Not Visible**: Check that the blend image is positioned within the base image bounds
- **Unexpected Results**: Different blend modes produce very different effects - experiment to find the right one

## Technical Details

The node supports multiple blend modes:

- **Mathematical Blends**: multiply, screen, overlay, soft_light, hard_light
- **Color Operations**: color_dodge, color_burn, difference, exclusion
- **Selection Blends**: darken, lighten
- **Standard Blending**: normal (alpha blending)

Each blend mode uses different mathematical operations to combine the pixel values, creating unique visual effects.
