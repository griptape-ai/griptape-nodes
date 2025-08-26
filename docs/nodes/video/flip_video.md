# FlipVideo

## What is it?

The FlipVideo node flips your video horizontally, vertically, or both directions. This creates a mirror effect that can be useful for correcting orientation or creating artistic effects.

## When would I use it?

Use the FlipVideo node when:

- You need to correct video that was recorded upside down or backwards
- You want to create mirror effects for artistic purposes
- You need to flip footage to match other video clips
- You're creating content that requires flipped orientation
- You want to create symmetrical video effects
- You need to correct camera orientation issues

## How to use it

### Basic Setup

1. Add a FlipVideo node to your workflow
1. Connect a video source to the "video" input
1. Choose the flip direction (horizontal, vertical, or both)
1. Run the workflow to flip the video

### Parameters

- **video**: The video content to flip (supports VideoArtifact and VideoUrlArtifact)

- **direction**: Flip direction (default: "horizontal")

    - "horizontal" = flip left to right (mirror effect)
    - "vertical" = flip top to bottom (upside down)
    - "both" = flip both horizontally and vertically

- **processing_speed**: Balance between processing speed and output quality (default: "balanced")

    - **fast**: Fastest processing, lower quality (ultrafast preset, CRF 30)
    - **balanced**: Good balance of speed and quality (medium preset, CRF 23)
    - **quality**: Highest quality, slower processing (slow preset, CRF 18)

### Outputs

- **video**: The flipped video, available as output to connect to other nodes

## Example

Imagine you want to create a mirror effect on a video:

1. Add a FlipVideo node to your workflow
1. Connect the video output from a LoadVideo node to the FlipVideo's "video" input
1. Set "direction" to "horizontal" to create a mirror effect
1. Run the workflow - the video will be flipped horizontally
1. The output filename will be `{original_filename}_flipped_horizontal.{format}`

## Important Notes

- The FlipVideo node uses FFmpeg with high-quality flip processing
- Horizontal flip creates a mirror effect (left becomes right)
- Vertical flip turns the video upside down
- Both directions flip the video in both axes
- The original audio track is preserved
- Processing time depends on video length and resolution
- Logs are available for debugging processing issues

## Direction Recommendations

- **For mirror effects**: Use "horizontal" - creates left-to-right mirror
- **For upside down correction**: Use "vertical" - flips top to bottom
- **For complete rotation**: Use "both" - flips in both directions
- **For camera correction**: Use appropriate direction based on how the camera was oriented

## Common Issues

- **Processing Timeout**: Large videos may take longer to process; the node has a 5-minute timeout
- **Wrong Direction**: Make sure you've selected the correct flip direction for your needs
- **No Video Input**: Make sure a video source is connected to the "video" input
- **FFmpeg Errors**: Check the logs parameter for detailed error information if processing fails
