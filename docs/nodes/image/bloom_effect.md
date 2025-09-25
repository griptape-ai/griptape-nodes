# BloomEffect

## What is it?

The BloomEffect node applies a beautiful bloom or glow effect to your images, creating dreamy, ethereal results. It simulates the way bright light sources create a soft, luminous halo around them, adding a magical quality to your images.

## When would I use it?

Use this node when you want to:

- Create dreamy, ethereal image effects
- Add a soft glow around bright areas
- Enhance the magical quality of fantasy or sci-fi images
- Create romantic or atmospheric lighting effects
- Add visual interest to portraits or landscapes
- Simulate lens flare or light bloom effects
- Enhance the mood and atmosphere of your images

## How to use it

### Basic Setup

1. Add the BloomEffect node to your workflow
1. Connect an image source to the "input_image" input
1. Adjust the bloom amount and radius sliders
1. The processed image will be available at the "output" parameter

### Parameters

#### Bloom Settings

- **bloom_amount** (0.0-2.0, default: 0.5): Controls the intensity of the bloom effect

    - 0.0 = no bloom effect
    - Higher values create more intense glow
    - 2.0 = maximum bloom intensity

- **bloom_radius** (1-20, default: 5): Controls the size of the bloom effect

    - Lower values create tighter, more focused glow
    - Higher values create larger, more diffuse glow
    - Larger radius values take longer to process

### Outputs

- **output**: The image with the bloom effect applied

## Example

A typical bloom effect workflow:

1. Load or generate an image using LoadImage or GenerateImage
1. Connect that image to the BloomEffect node's "input_image" parameter
1. Adjust the bloom settings:
    - Set bloom_amount to 0.8 for a moderate glow effect
    - Set bloom_radius to 8 for a medium-sized bloom
1. Connect the "output" to DisplayImage to view the result

## Important Notes

- **Live Preview**: Changes are applied in real-time as you move the sliders
- **Processing Time**: Larger radius values take longer to process
- **Best Results**: Works best on images with bright areas or light sources
- **RGBA Support**: The node preserves transparency in RGBA images

## Common Issues

- **No Visible Effect**: Make sure bloom_amount is greater than 0
- **Too Subtle**: Increase bloom_amount for more visible effect
- **Too Strong**: Decrease bloom_amount for more subtle effect
- **Slow Processing**: Reduce bloom_radius for faster processing

## Technical Details

The bloom effect is created by:

1. **Brightness Detection**: Identifying bright areas in the image
1. **Gaussian Blur**: Applying blur to create the glow effect
1. **Blending**: Combining the original image with the blurred version
1. **Intensity Control**: Scaling the effect based on bloom_amount

This creates a realistic bloom effect similar to what you'd see in professional photography or film.
