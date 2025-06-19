# ResizeVideo

## What is it?

The ResizeVideo node allows you to resize video content by a specified percentage using FFmpeg. It can scale videos up or down while maintaining the original aspect ratio and ensuring compatibility with video codecs.

## When would I use it?

Use the ResizeVideo node when:

- You need to reduce video file size for storage or transmission
- You want to scale up videos for better quality on larger displays
- You need to standardize video dimensions across multiple files
- You want to optimize videos for specific platforms or devices
- You need to process videos to meet size or resolution requirements

## How to use it

### Basic Setup

1. Add a ResizeVideo node to your workflow
1. Connect a video source to the "video" input
1. Set the "percentage" parameter to your desired resize amount (1-100)
1. Run the workflow to resize the video

### Parameters

- **video**: The video content to resize (supports VideoArtifact and VideoUrlArtifact)

- **percentage**: The resize percentage as an integer (1-100, default: 50)

    - 50 = 50% of original size
    - 200 = 200% of original size (scaled up)
    - 25 = 25% of original size (scaled down)

### Outputs

- **resized_video**: The resized video content, available as output to connect to other nodes

## Example

Imagine you want to resize a large video file to 50% of its original size:

1. Add a ResizeVideo node to your workflow
1. Connect the video output from a LoadVideo node to the ResizeVideo's "video" input
1. Set the "percentage" parameter to 50
1. Run the workflow - the video will be resized to 50% of its original dimensions
1. The output filename will be `{original_filename}_resized_50.{format}`

## Important Notes

- The ResizeVideo node uses FFmpeg for high-quality video processing
- Dimensions are automatically adjusted to be divisible by 2 for codec compatibility
- The original aspect ratio is preserved during resizing
- The node supports common video formats (mp4, avi, mov, etc.)
- Processing time depends on video size and complexity
- The resized video maintains the original audio track
- Logs are available for debugging processing issues

## Common Issues

- **Processing Timeout**: Large videos may take longer to process; the node has a 5-minute timeout
- **Invalid Percentage**: Make sure the percentage is between 1 and 100
- **Unsupported Format**: Check that your input video is in a supported format
- **No Video Input**: Make sure a video source is connected to the "video" input
- **FFmpeg Errors**: Check the logs parameter for detailed error information if processing fails
