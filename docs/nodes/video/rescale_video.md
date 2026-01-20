# RescaleVideo

## What is it?

The RescaleVideo node resizes video content using different modes (width, height, percentage, or width and height) with FFmpeg, while preserving or adjusting aspect ratio based on your fit mode choice.

## When would I use it?

Use the RescaleVideo node when:

- You need to scale videos by a precise percentage
- You want to target a specific width or height while preserving aspect ratio
- You need to fit videos into exact dimensions with padding or cropping
- You want consistent size options similar to the RescaleImage node

## How to use it

### Basic Setup

1. Add a RescaleVideo node to your workflow
1. Connect a video source to the "video" input
1. Select a "resize_mode"
1. Configure the matching size parameters
1. Run the workflow to rescale the video

### Parameters

- **video**: The video content to rescale (supports VideoArtifact and VideoUrlArtifact)

- **resize_mode**: How the video should be rescaled

    - `width`: Resize to a target width while preserving aspect ratio
    - `height`: Resize to a target height while preserving aspect ratio
    - `percentage`: Resize by a percentage of the original size
    - `width and height`: Resize to exact dimensions with fit options

- **target_size**: Target size in pixels for width/height modes (1-8000)

- **percentage_scale**: Scale factor as a percentage (1-500, default: 100)

- **target_width**: Target width in pixels for width and height mode

- **target_height**: Target height in pixels for width and height mode

- **fit_mode**: How to fit the video within the target dimensions

    - `fit`: Preserve aspect ratio and add padding (letterboxing)
    - `fill`: Preserve aspect ratio and crop to fill the target
    - `stretch`: Ignore aspect ratio and stretch to the target

- **background_color**: Background color for letterboxing in fit mode (hex)

- **resample_filter**: Resampling filter used for scaling

    - `neighbor`, `bilinear`, `bicubic`, `lanczos`

- **output_frame_rate**: Output frame rate selection (auto or specific values)

- **processing_speed**: Encoding speed vs quality

### Outputs

- **output**: The rescaled video as a VideoUrlArtifact

## Example

To resize a video to 1280x720 while preserving aspect ratio with padding:

1. Set **resize_mode** to `width and height`
1. Set **target_width** to `1280`
1. Set **target_height** to `720`
1. Set **fit_mode** to `fit`
1. Set **background_color** to `#000000`

## Important Notes

- Width and height are rounded to even values for codec compatibility
- The node uses FFmpeg and preserves audio when available
- Logs are available for troubleshooting if processing fails
