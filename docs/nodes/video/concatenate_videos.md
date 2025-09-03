# ConcatenateVideos

## What is it?

The ConcatenateVideos node combines multiple videos into a single continuous video file with configurable format and codec options. It automatically handles videos of different dimensions by resizing them to match the first video's dimensions, ensuring smooth concatenation without visual discontinuity.

## When would I use it?

Use the ConcatenateVideos node when:

- You want to combine multiple video clips into one continuous video
- Creating video compilations or montages from separate clips
- Joining video segments that were split or recorded separately
- Building longer videos from shorter generated clips (like from AI video models)
- Creating playlists or sequences from individual video files
- Combining videos with different resolutions (automatic resizing handles dimension mismatches)

## How to use it

### Basic Setup

1. Add a ConcatenateVideos node to your workflow
1. Connect multiple video inputs to the **video_inputs** parameter (can connect individual videos or a list)
1. Configure the output format and codec settings as needed
1. Connect the **output** to other nodes that require video input

### Parameters

- **video_inputs**: List of videos to concatenate (supports VideoArtifact, VideoUrlArtifact, and lists of both types)
- **output_format**: Output video format - mp4, avi, mov, mkv, or webm (default: mp4)
- **video_codec**: Video codec for output - libx264, libx265, libvpx-vp9, or copy (default: libx264)
- **audio_codec**: Audio codec for output - aac, mp3, libmp3lame, or copy (default: aac)
- **output_frame_rate**: Frame rate control (inherited from BaseVideoProcessor)
- **processing_speed**: Quality vs speed trade-off (inherited from BaseVideoProcessor)

### Outputs

- **output**: The concatenated video file as a VideoUrlArtifact
- **logs**: Processing logs with detailed information about downloading, dimension checking, and resizing operations

## Automatic Video Resizing

The ConcatenateVideos node intelligently handles videos with different dimensions by automatically resizing them:

### How It Works

1. **Dimension Detection**: The node checks the dimensions of all input videos using FFprobe
1. **Reference Selection**: The first video's dimensions are used as the target size for all videos
1. **Smart Resizing**: Videos that don't match the target dimensions are automatically resized using FFmpeg
1. **Aspect Ratio Preservation**: Resizing maintains the original aspect ratio and adds black padding if needed
1. **Detailed Logging**: All resizing operations are logged with before/after dimensions

### Resizing Behavior

- **Same Size Videos**: If all videos have matching dimensions, no resizing occurs
- **Mixed Size Videos**: Videos are resized to match the first video's dimensions
- **Quality Preservation**: Uses high-quality scaling with aspect ratio preservation
- **Audio Preservation**: Audio tracks are copied without re-encoding during resize operations

### Log Examples

When videos have matching dimensions:

```
✅ All videos have matching dimensions - no resizing needed
```

When resizing is needed:

```
🔄 Videos have different dimensions - resizing to match first video...
Target dimensions (from first video): 1920x1080
• Video 1: 1920x1080 (reference)
• Video 2: 1280x720 → 1920x1080 (resizing...)
  ✅ Video 2 resized successfully
• Video 3: 1920x1080 (no resize needed)
```

## Example

When creating a longer video from multiple AI-generated clips:

1. Add a ConcatenateVideos node to your workflow
1. Connect multiple video generation nodes to the **video_inputs** parameter
1. Set the **output_format** to "mp4" and **video_codec** to "libx264" for wide compatibility
1. Set the **audio_codec** to "aac" for high-quality audio
1. When the node runs, all input videos will be joined into a single continuous video

## Advanced Usage

### Format and Codec Selection

- **mp4 + libx264**: Best for web compatibility and general use
- **mov + libx264**: Good for professional video editing workflows
- **mkv + libx265**: Excellent compression for storage efficiency
- **webm + libvpx-vp9**: Optimized for web streaming
- **copy codecs**: Fastest processing when all inputs have the same codec

### Performance Tips

- Use "copy" for video and audio codecs when all input videos have identical formats for fastest processing
- Choose "fast" processing speed for quick previews, "quality" for final output
- Consider using libx265 for smaller file sizes with similar quality
- **For best performance**: Use videos with matching dimensions to avoid resizing overhead
- **Video ordering**: Place your highest-quality or target-dimension video first to set the reference resolution

## Important Notes

- **Minimum Input**: Requires at least 2 videos to concatenate
- **Format Support**: Supports common video formats (mp4, avi, mov, mkv, webm)
- **Automatic Download**: Videos are automatically downloaded and prepared for concatenation
- **Automatic Resizing**: Videos with different dimensions are automatically resized to match the first video
- **Dimension Reference**: The first video in the list determines the target dimensions for all videos
- **Quality Preservation**: Resizing uses high-quality FFmpeg scaling with aspect ratio preservation
- **Frame Rate Handling**: Can automatically adjust frame rates or preserve original rates
- **Audio Synchronization**: Maintains audio sync throughout the concatenated video
- **Web Optimization**: Adds faststart flag for optimized web streaming
- **Processing Logs**: Detailed logs show all dimension checking and resizing operations

## Common Issues

- **"At least 2 videos required"**: Make sure you've connected at least two video inputs to the node
- **Format Mismatch**: If videos have very different formats, avoid using "copy" codecs and let the node re-encode
- **Large File Processing**: For very large videos, increase timeout or use "fast" processing speed
- **Audio Issues**: If source videos have different audio formats, avoid "copy" audio codec and use aac or mp3
- **Memory Usage**: Processing many large videos simultaneously may require sufficient system memory
- **Slow Resizing**: Large videos with different dimensions will take longer to process due to resizing operations
- **Unexpected Dimensions**: The first video determines output dimensions - reorder videos if you want different target dimensions
- **Quality Loss**: Multiple resizing operations may reduce video quality - use videos with matching dimensions when possible
- **FFprobe Errors**: If dimension detection fails, ensure videos are valid and not corrupted
