# AddOverlay

## What is it?

The AddOverlay node composites two videos together by overlaying one video on top of another using FFmpeg's blend modes. It provides control over the blend mode, channel selection, and sizing of the overlay video. The node supports various blend modes that match industry-standard compositing software.

## When would I use it?

Use the AddOverlay node when:

- You want to add film grain or noise effects to your video
- You need to composite multiple video layers together
- You're creating videos with watermarks or logos
- You want to add visual effects that require layering
- You're working on projects that need video compositing
- You want to create vintage or textured video effects

## How to use it

### Basic Setup

1. Add an AddOverlay node to your workflow
1. Connect a base video to the "video" input
1. Connect an overlay video to the "overlay_video" input
1. Choose a blend mode and adjust the amount parameter
1. Run the workflow to composite the videos

### Parameters

- **video**: The base video content (supports VideoArtifact and VideoUrlArtifact)

- **overlay_video**: The video or image to overlay on top of the base video (supports VideoArtifact, VideoUrlArtifact, ImageArtifact, and ImageUrlArtifact)

- **blend_mode**: How to blend the overlay with the base video (default: "overlay")

    - **overlay**: Original overlay with alpha blending
    - **screen**: Brighten (good for dust/scratches)
    - **lighten**: Only brighten where overlay is brighter
    - **softlight**: Natural blending for film grain
    - **grainmerge**: Merge grain/noise (recommended for noise effects)
    - **grainextract**: Extract grain/noise
    - **glow**: Glow effect
    - **hardlight**: Hard light blending

- **amount**: Strength of the overlay effect (0.0-1.0, default: 0.5)

    - 0.0 = no effect (original video unchanged)
    - 0.5 = 50% effect strength (default)
    - 1.0 = full effect strength

- **processing_speed**: Balance between processing speed and output quality (default: "balanced")

    - **fast**: Fastest processing, lower quality (ultrafast preset, CRF 30)
    - **balanced**: Good balance of speed and quality (medium preset, CRF 23)
    - **quality**: Highest quality, slower processing (slow preset, CRF 18)

### Outputs

- **video**: The composited video with overlay applied, available as output to connect to other nodes

## Examples

### Example 1: Film Grain Overlay

1. Connect a base video to the AddOverlay's "video" input
1. Connect a film grain video to the "overlay_video" input
1. Set "blend_mode" to "grainmerge" for noise effects
1. Set "amount" to 0.3 for subtle grain effect
1. Run the workflow - the video will have a film grain overlay
1. The output filename will be `{original_filename}_overlay_grainmerge_amount0.30.{format}`

### Example 2: Logo Overlay

1. Connect a base video to the AddOverlay's "video" input
1. Connect a PNG logo with transparency to the "overlay_video" input
1. Set "blend_mode" to "overlay" for alpha blending
1. Set "amount" to 0.8 for visible logo
1. Run the workflow - the video will have a positioned logo

### Example 3: Vintage Effect with Film Grain

1. Use ChangeSpeed to speed up your video
1. Use AddColorCurves with "vintage" preset
1. Use AddOverlay to add film grain texture
1. Set "blend_mode" to "grainmerge"
1. Set "amount" to 0.4 for vintage grain effect
1. Run the workflow for a complete vintage look

## Important Notes

- The overlay video will be automatically looped and trimmed to match the base video's duration
- PNG images with transparency are supported as overlays
- The node uses linear RGB blending for consistent results that match industry standards
- For noise effects, use "grainmerge" blend mode with "luminance" channel
- For logos with transparency, use "overlay" blend mode with "rgba" channel
- The overlay is always centered on the base video for simplicity

## Technical Details

The node uses FFmpeg's blend modes and supports both overlay filter (for alpha blending) and blend filter (for other blend modes). It automatically converts to linear RGB space for consistent blending behavior that matches industry-standard compositing software.
