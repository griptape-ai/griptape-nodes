# ResizeVideo

## What is it?

The ResizeVideo node resizes video content using multiple scaling modes (width, height, percentage, or width and height) with FFmpeg. It can preserve aspect ratio, pad with a background color, or crop to fill depending on your fit mode.

## When would I use it?

Use the ResizeVideo node when:

- You need to scale videos by a precise percentage
- You want to target a specific width or height while preserving aspect ratio
- You need to fit videos into exact dimensions with padding or cropping
- You want consistent resizing controls across video workflows

## How to use it

### Basic Setup

1. Add a ResizeVideo node to your workflow
1. Connect a video source to the "video" input
1. Choose a "resize_mode"
1. Configure the size parameters for that mode
1. Run the workflow to resize the video

### Parameters

- **video**: The video content to resize (supports VideoArtifact and VideoUrlArtifact)

- **resize_mode**: How the video should be resized

    - `width`: Resize to a target width while preserving aspect ratio
    - `height`: Resize to a target height while preserving aspect ratio
    - `percentage`: Resize by a percentage of the original size
    - `width and height`: Resize to exact dimensions with fit options

- **target_size**: Target size in pixels for width/height modes (1-8000)

- **percentage**: Resize percentage (1-500, default: 100)

- **target_width**: Target width in pixels for width and height mode

- **target_height**: Target height in pixels for width and height mode

- **fit_mode**: How to fit the video within the target dimensions

    - `fit`: Preserve aspect ratio and add padding (letterboxing)
    - `fill`: Preserve aspect ratio and crop to fill the target
    - `stretch`: Ignore aspect ratio and stretch to the target

- **background_color**: Background color for letterboxing in fit mode (hex)

- **scaling_algorithm**: The scaling algorithm used for resizing (default: "bicubic")

    - `neighbor`, `bilinear`, `bicubic`, `lanczos`

- **lanczos_parameter**: Fine-tune the Lanczos scaling algorithm (1.0-10.0, default: 3.0)

    Only affects the output when `scaling_algorithm` is set to "lanczos".

### Outputs

- **resized_video**: The resized video content, available as output to connect to other nodes

## Example

To resize a video to 1280x720 while preserving aspect ratio with padding:

1. Set **resize_mode** to `width and height`
1. Set **target_width** to `1280`
1. Set **target_height** to `720`
1. Set **fit_mode** to `fit`
1. Set **background_color** to `#000000`

## Important Notes

- The ResizeVideo node uses FFmpeg for video processing
- Dimensions are automatically adjusted to be divisible by 2 for codec compatibility
- The node supports common video formats (mp4, avi, mov, etc.)
- The resized video maintains the original audio track
- Logs are available for debugging processing issues
