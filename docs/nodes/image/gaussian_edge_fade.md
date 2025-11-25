# Gaussian Edge Fade

## Overview

The **Gaussian Edge Fade** node applies a Gaussian-blurred alpha channel fade to image edges for smooth compositing. This creates smooth transitions at the edges of images, making them ideal for overlaying on other images or backgrounds without harsh borders.

## Use Cases

- **Image Compositing**: Seamlessly blend images together with smooth edge transitions
- **Vignette Effects**: Create professional vignette-style edge fading
- **Overlay Preparation**: Prepare images for overlay on varied backgrounds
- **Logo Processing**: Add edge fading to logos with transparent backgrounds while preserving cutouts
- **Photo Editing**: Create organic, natural-looking edge fades with rounded corners

## Parameters

### Input Parameters

| Parameter         | Type                             | Description                                                                                                                                                                 |
| ----------------- | -------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **input_image**   | ImageArtifact / ImageUrlArtifact | The input image to apply edge fade to                                                                                                                                       |
| **fade_mode**     | String                           | How to measure fade distance: "percentage" (relative to image size) or "pixels" (absolute distance). Default: "percentage"                                                  |
| **fade_distance** | Integer                          | Distance from edge to fade. In percentage mode: 5 = 5% of image dimension. In pixels mode: 5 = 5 pixels. Default: 5                                                         |
| **blur_radius**   | Integer                          | Gaussian blur radius for smooth edge transition (0-100). Higher values create softer fades. Default: 10                                                                     |
| **fade_curve**    | Float                            | Controls transparency transition shape (0.5-4.0). 1.0 = linear, >1.0 = more transparent near edges (aggressive), \<1.0 = less transparent near edges (gentle). Default: 2.0 |
| **edge_shape**    | String                           | Shape of the fade: "square" (straight edges) or "rounded" (curved corners). Default: "square"                                                                               |
| **replace_mask**  | Boolean                          | If False, combines edge fade with existing alpha channel. If True, replaces existing alpha entirely. Default: False                                                         |
| **apply_top**     | Boolean                          | Apply fade to top edge. Default: True                                                                                                                                       |
| **apply_bottom**  | Boolean                          | Apply fade to bottom edge. Default: True                                                                                                                                    |
| **apply_left**    | Boolean                          | Apply fade to left edge. Default: True                                                                                                                                      |
| **apply_right**   | Boolean                          | Apply fade to right edge. Default: True                                                                                                                                     |

### Output Parameters

| Parameter        | Type             | Description                                      |
| ---------------- | ---------------- | ------------------------------------------------ |
| **output_image** | ImageUrlArtifact | The processed image with alpha channel edge fade |

## Key Features

### Fade Modes

**Percentage Mode**: Resolution-independent fading that scales with image size. A 5% fade looks consistent across images of any size.

**Pixels Mode**: Fixed-size fading with precise pixel control. A 50-pixel fade is the same absolute distance regardless of image size.

### Fade Curve

The fade curve parameter uses a power function to control how transparency transitions from edge to center:

- **0.5-0.9**: Gentle curve - edges stay MORE opaque with quick transition to full opacity
- **1.0**: Linear - even transition from transparent to opaque
- **2.0 (Default)**: Aggressive - edges stay MORE transparent with gradual transition
- **3.0-4.0**: Very aggressive - extreme transparency at edges, very gradual fade

### Edge Shapes

**Square**: Each edge fades independently, creating straight transitions. Best for traditional vignettes and letterbox effects.

**Rounded**: Fade follows curved contours using distance field calculations, creating smooth organic corner transitions. Best for modern UI designs and natural photo compositing.

### Alpha Channel Handling

**Replace Mask = False (Default)**: Preserves existing transparency and combines it with the edge fade using multiplicative blending. Perfect for logos with transparent backgrounds.

**Replace Mask = True**: Ignores existing alpha channel and applies only the new edge fade. Useful for images with unwanted transparency.

## Example Usage

### Basic Vignette Effect

1. Connect an image to **input_image**
1. Set **fade_mode** to "percentage"
1. Set **fade_distance** to 10 (10%)
1. Set **blur_radius** to 15
1. Set **fade_curve** to 2.0
1. Keep all **apply\_**\* edges set to True
1. Run the node

Result: Image with soft, even fade on all edges.

### Letterbox Effect

1. Connect an image to **input_image**
1. Set **fade_mode** to "pixels"
1. Set **fade_distance** to 50
1. Set **blur_radius** to 20
1. Set **apply_top** and **apply_bottom** to True
1. Set **apply_left** and **apply_right** to False
1. Run the node

Result: Horizontal fades only, suitable for widescreen overlays.

### Rounded Corner Composite

1. Connect an image to **input_image**
1. Set **edge_shape** to "rounded"
1. Set **fade_mode** to "percentage"
1. Set **fade_distance** to 8
1. Set **blur_radius** to 12
1. Set **fade_curve** to 2.5 (aggressive)
1. Run the node

Result: Image with smooth rounded corners perfect for modern UI compositing.

### Preserve Logo Transparency

1. Connect a logo PNG with transparent background to **input_image**
1. Set **replace_mask** to False
1. Set **fade_distance** to 5
1. Set **blur_radius** to 10
1. Run the node

Result: Logo keeps its transparent cutouts while adding smooth edge fade.

## Tips

- **For natural compositing**: Use fade_curve values between 2.0-3.0 for more transparency at edges
- **For resolution-independent effects**: Use percentage mode with consistent values across different image sizes
- **For rounded corners**: Combine edge_shape "rounded" with all edges enabled for organic oval shapes
- **For selective fading**: Disable specific edges to create directional fades
- **For text overlays**: Use gentle fade_curve (0.7-0.9) to keep edges more visible

## Technical Notes

- Output format is RGBA PNG with alpha channel preserved
- Supports any input image format that PIL can process
- Uses NumPy for efficient gradient calculations
- Applies Gaussian blur using PIL's ImageFilter for smooth transitions
- Multiplicative alpha blending when combining with existing alpha channels
- Automatically clamps fade distance to prevent artifacts when exceeding image dimensions
