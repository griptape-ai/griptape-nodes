# ColorMatch

## What is it?

The ColorMatch node transfers color characteristics from a reference image to a target image using various color matching algorithms. This is useful for automatic color grading, matching the look and feel between images, correcting lighting inconsistencies, and creating consistent visual styles across multiple images.

## When would I use it?

Use this node when you want to:

- Match colors between two images for consistency
- Apply color grading from one image to another
- Correct lighting inconsistencies between shots
- Create a unified color palette across multiple images
- Transfer the mood or atmosphere of a reference image
- Color-match stop-motion or video frames
- Apply a color style from a reference photo

## How to use it

### Basic Setup

1. Add the ColorMatch node to your workflow
1. Connect the reference image to "reference_image" (the image with the color palette you want to copy)
1. Connect the target image to "target_image" (the image you want to modify)
1. Select a color transfer method
1. Adjust the strength parameter as needed
1. The color-matched image will be available at the "output" parameter

### Parameters

#### Image Inputs

- **reference_image**: The reference image providing the color palette to transfer
- **target_image**: The target image to apply color transfer to (will be modified)

#### Color Match Settings

- **method**: The color transfer algorithm to use

    - **mkl**: Monge-Kantorovich Linearization (fast, good quality, default)
    - **hm**: Histogram Matching (fast, moderate quality)
    - **reinhard**: Reinhard et al. color transfer (fast, good quality)
    - **mvgd**: Multi-Variate Gaussian Distribution (medium speed, good quality)
    - **hm-mvgd-hm**: Compound method (slower, best quality)
    - **hm-mkl-hm**: Alternative compound method (slower, best quality)

- **strength** (0.0-10.0, default: 1.0): Controls the intensity of the color transfer

    - 0.0 = no change (original image)
    - 1.0 = full color transfer
    - Values > 1.0 exaggerate the effect

### Outputs

- **output**: The color-matched image with transferred color characteristics

## Example

A typical color matching workflow:

1. Load two images using LoadImage nodes
1. Connect the image you want to modify to "input_image"
1. Connect the reference image (with the desired colors) to "reference_image"
1. Select the "mkl" method for a good balance of speed and quality
1. Set strength to 1.0 for full color transfer
1. Connect the "output" to DisplayImage to view the result
1. Adjust strength if the effect is too strong or too subtle

### Use Cases

#### Photo Color Grading

Match the color palette of a professionally graded photo to your own images:

1. Load your photo as the target image
1. Load the reference photo with the desired color grading
1. Use "reinhard" or "mkl" method
1. Adjust strength to taste (0.7-1.0 for subtle, 1.0-1.5 for dramatic)

#### Stop-Motion Correction

Correct lighting inconsistencies between stop-motion frames:

1. Load a frame with correct lighting as the reference
1. Load frames that need correction as target images
1. Use "mkl" method for fast processing
1. Set strength to 1.0 for accurate matching

#### Batch Style Transfer

Apply a consistent color style across multiple images:

1. Load your style reference image
1. Process each target image through the ColorMatch node
1. Use "hm-mvgd-hm" for highest quality results

## Important Notes

- **Live Preview**: Changes are applied in real-time as you adjust parameters
- **RGB Processing**: Images are converted to RGB for processing
- **Preserves Dimensions**: Output image maintains the same dimensions as the target image
- **Algorithm Differences**: Different methods produce subtly different results - experiment to find the best one for your use case

## Common Issues

- **No Change Visible**: Make sure strength is greater than 0
- **Effect Too Strong**: Reduce the strength value below 1.0
- **Unexpected Colors**: Try a different method - "reinhard" often produces more natural results
- **Slow Processing**: Use "mkl" or "hm" for faster results; avoid compound methods for large images

## Technical Details

The node uses the color-matcher library to perform color transfer. The available algorithms are:

- **MKL (Monge-Kantorovich Linearization)**: Uses optimal transport theory to match color distributions
- **HM (Histogram Matching)**: Matches the histogram of each color channel independently
- **Reinhard**: Classic color transfer method based on decorrelated color spaces
- **MVGD (Multi-Variate Gaussian Distribution)**: Matches the mean and covariance of color distributions
- **Compound Methods**: Combine multiple algorithms for improved results

The strength parameter uses linear interpolation: `result = target + strength * (matched - target)`
