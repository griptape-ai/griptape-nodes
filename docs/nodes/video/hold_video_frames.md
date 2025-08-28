# HoldVideoFrames

## What is it?

The HoldVideoFrames node creates a stepped video effect by holding each frame for a specified number of frames. This creates a stop-motion or frame-stepping effect that can add artistic interest to your video content.

## When would I use it?

Use the HoldVideoFrames node when:

- You want to create a stop-motion animation effect
- You need to slow down fast-moving content for better visibility
- You're creating artistic video effects with frame manipulation
- You want to add a retro or vintage feel to your video
- You need to create dramatic slow-motion effects
- You're making content that requires frame-by-frame analysis

## How to use it

### Basic Setup

1. Add a HoldVideoFrames node to your workflow
1. Connect a video source to the "video" input
1. Set the "hold_frames" parameter to specify how many frames to hold
1. Run the workflow to create the frame-holding effect

### Parameters

- **video**: The video content to apply frame holding to (supports VideoArtifact and VideoUrlArtifact)

- **hold_frames**: Number of frames to hold (1-10, default: 2)

    - 1 = no effect (normal playback)
    - 2 = each frame held for 2 frames (slower playback)
    - 5 = each frame held for 5 frames (much slower playback)
    - 10 = each frame held for 10 frames (very slow playback)

- **processing_speed**: Balance between processing speed and output quality (default: "balanced")

    - **fast**: Fastest processing, lower quality (ultrafast preset, CRF 30)
    - **balanced**: Good balance of speed and quality (medium preset, CRF 23)
    - **quality**: Highest quality, slower processing (slow preset, CRF 18)

### Outputs

- **video**: The video with frame holding effect applied, available as output to connect to other nodes

## Example

Imagine you want to create a stop-motion effect on a video:

1. Add a HoldVideoFrames node to your workflow
1. Connect the video output from a LoadVideo node to the HoldVideoFrames's "video" input
1. Set "hold_frames" to 3 to hold each frame for 3 frames
1. Run the workflow - the video will have a stepped, stop-motion effect
1. The output filename will be `{original_filename}_hold_3_frames.{format}`

## Important Notes

- The HoldVideoFrames node uses FFmpeg with high-quality frame processing
- The effect reduces the effective frame rate by the hold_frames value
- The original audio track is preserved but may not sync perfectly with the visual effect
- Processing time depends on video length and hold_frames value
- Logs are available for debugging processing issues

## Effect Recommendations

- **Subtle slow motion**: Use hold_frames 2-3 for gentle frame holding
- **Stop-motion effect**: Use hold_frames 4-6 for noticeable stepping
- **Dramatic slow motion**: Use hold_frames 7-10 for very slow playback
- **Frame analysis**: Use hold_frames 2-3 to slow down fast content for review

## Common Issues

- **Processing Timeout**: Large videos may take longer to process; the node has a 5-minute timeout
- **Effect Too Strong**: Reduce hold_frames value if the effect is too dramatic
- **Audio Sync Issues**: The frame holding may affect audio synchronization
- **No Video Input**: Make sure a video source is connected to the "video" input
- **FFmpeg Errors**: Check the logs parameter for detailed error information if processing fails
