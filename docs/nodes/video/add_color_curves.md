# AddColorCurves

## What is it?

The AddColorCurves node applies color grading effects to video using FFmpeg's `curves` filter. This filter allows for sophisticated color manipulation by adjusting the tonal curves of the video, providing both built-in presets and custom curve options for advanced color grading.

## When would I use it?

Use the AddColorCurves node when:

- You want to apply cinematic color grading effects to your video
- You need to match the color style of multiple video clips
- You're creating content that requires a specific visual aesthetic
- You want to enhance the mood and atmosphere of your video
- You need professional color correction and grading
- You're working on projects that require consistent color treatment

## How to use it

### Basic Setup

1. Add an AddColorCurves node to your workflow
1. Connect a video source to the "video" input
1. Select a curve preset or define custom curves
1. Run the workflow to apply the color grading

### Parameters

- **video**: The video content to apply color curves to (supports VideoArtifact and VideoUrlArtifact)

- **curve_preset**: Built-in curve preset for color grading effects (default: "none")

    - **none**: No curves applied
    - **color_negative**: Color negative film look
    - **cross_process**: Cross-processed film effect
    - **darker**: Darker overall tone
    - **increase_contrast**: Moderate contrast boost
    - **lighter**: Lighter overall tone
    - **linear_contrast**: Linear contrast adjustment
    - **medium_contrast**: Medium contrast enhancement
    - **negative**: Black and white negative effect
    - **strong_contrast**: High contrast dramatic look
    - **vintage**: Classic vintage film look

- **processing_speed**: Balance between processing speed and output quality (default: "balanced")

    - **fast**: Fastest processing, lower quality (ultrafast preset, CRF 30)
    - **balanced**: Good balance of speed and quality (medium preset, CRF 23)
    - **quality**: Highest quality, slower processing (slow preset, CRF 18)

### Outputs

- **video**: The video with color curves applied, available as output to connect to other nodes

## Examples

### Example 1: Apply Vintage Effect

1. Connect the video output from a LoadVideo node to the AddColorCurves's "video" input
1. Set "curve_preset" to "vintage"
1. Run the workflow - the video will have a classic vintage film look
1. The output filename will be `{original_filename}_curves_vintage.{format}`

### Example 2: Apply Strong Contrast

1. Connect a video to the AddColorCurves node
1. Set "curve_preset" to "strong_contrast"
1. Run the workflow - the video will have dramatic contrast enhancement
1. The output filename will be `{original_filename}_curves_strong_contrast.{format}`

### Example 3: Apply Cross-Process Effect

1. Connect a video to the AddColorCurves node
1. Set "curve_preset" to "cross_process"
1. Run the workflow - the video will have a cross-processed film look
1. The output filename will be `{original_filename}_curves_cross_process.{format}`

## Important Notes

- The AddColorCurves node uses FFmpeg's curves filter for high-quality color grading
- Built-in presets provide quick access to common color grading effects
- Processing time depends on video length and resolution
- Curves can significantly affect the visual mood and style of your video
- For best results, apply curves after other color adjustments

## Parameter Recommendations

### For Cinematic Look

- Use "vintage" or "cross_process" presets
- Try "color_negative" for a unique film look

### For High Contrast

- Use "strong_contrast" or "negative"
- Try "increase_contrast" for subtle enhancement
