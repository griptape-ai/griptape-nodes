# ChangeSpeed

## What is it?

The ChangeSpeed node allows you to change the playback speed of a video. It uses FFmpeg's setpts filter to adjust video timing and automatically adjusts audio speed to match, creating smooth speed changes while maintaining audio-video synchronization.

## When would I use it?

Use the ChangeSpeed node when:

- You want to create fast-motion effects (e.g., 2x, 3x faster)
- You need to create slow-motion effects (e.g., 0.5x, 0.25x slower)
- You want to speed up long videos for quick review
- You need to slow down fast action for analysis
- You're creating time-lapse or slow-motion content
- You want to adjust video pacing for different audiences

## How to use it

### Basic Setup

1. Add a ChangeSpeed node to your workflow
1. Connect a video source to the "video" input
1. Set your desired speed multiplier
1. Run the workflow to change the video's playback speed

### Parameters

- **video**: The video content to change speed (supports VideoArtifact and VideoUrlArtifact)

- **speed**: Playback speed multiplier (0.1-10.0x, default: 1.0)

    - 0.1 = 10x slower (very slow motion)
    - 0.5 = 2x slower (slow motion)
    - 1.0 = normal speed (default)
    - 2.0 = 2x faster (fast motion)
    - 5.0 = 5x faster (very fast motion)
    - 10.0 = 10x faster (maximum speed)

- **include_audio**: When enabled, includes audio in the output file (default: true)

    - When enabled: Audio is speed-adjusted to match video speed
    - When disabled: Creates a silent video (no audio track)

### Outputs

- **video**: The video with changed playback speed, available as output to connect to other nodes

## Example

Imagine you want to create a fast-motion effect by speeding up a video 3x:

1. Add a ChangeSpeed node to your workflow
1. Connect the video output from a LoadVideo node to the ChangeSpeed's "video" input
1. Set "speed" to 3.0 for 3x faster playback
1. Keep "include_audio" enabled (default) to include speed-adjusted audio
1. Run the workflow - the video will play 3x faster with audio adjusted to match
1. The output filename will be `{original_filename}_speed3.0.{format}`

## Important Notes

- The ChangeSpeed node uses FFmpeg's setpts filter for high-quality speed changes
- Audio is automatically speed-adjusted using the atempo filter to maintain synchronization (when include_audio is enabled)
- Speed changes affect both video and audio simultaneously
- Processing time depends on video length and resolution
- Extreme speed changes (very fast or very slow) may affect audio quality
- When include_audio is disabled, the output video will be silent

## Parameter Recommendations

- **For fast motion**: Use 2.0-5.0 for sped-up effects
- **For slow motion**: Use 0.25-0.75 for slow-motion effects
- **For time-lapse**: Use 5.0-10.0 for very fast playback
- **For analysis**: Use 0.5-0.75 to slow down fast action
- **For quick review**: Use 2.0-3.0 to speed up long content

## Common Issues

- **Processing Timeout**: Large videos may take longer to process; the node has a 5-minute timeout
- **Audio Quality**: Extreme speed changes may affect audio clarity
- **No Video Input**: Make sure a video source is connected to the "video" input
- **FFmpeg Errors**: Check the logs parameter for detailed error information if processing fails

## Speed Examples

- **0.25x**: 4x slower - Good for analyzing fast action
- **0.5x**: 2x slower - Classic slow motion
- **1.0x**: Normal speed - No change
- **2.0x**: 2x faster - Fast motion
- **3.0x**: 3x faster - Very fast motion
- **5.0x**: 5x faster - Time-lapse effect
