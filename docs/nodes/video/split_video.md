# SplitVideo

## What is it?

The SplitVideo node allows you to split a video into multiple segments using timecodes. It uses AI-powered parsing to understand various timecode formats and creates separate video files for each segment while maintaining high quality.

## When would I use it?

Use the SplitVideo node when:

- You need to break a long video into smaller, manageable segments
- You want to extract specific scenes or sections from a video
- You're creating video clips for social media or different platforms
- You need to separate different parts of a recording (intro, main content, outro)
- You want to create highlight reels from longer footage
- You're preparing video content for different audiences or purposes

## How to use it

### Basic Setup

1. Add a SplitVideo node to your workflow
1. Connect a video source to the "video" input
1. Enter timecodes in the "timecodes" parameter
1. Run the workflow to split the video into segments

### Parameters

- **video**: The video to split (supports VideoArtifact and VideoUrlArtifact)

- **timecodes**: Timecodes to split the video at (required)

    Supports various formats:

    **Simple timecode ranges:**

    ```
    00:00:00:00-00:01:00:00
    00:01:00:00-00:02:30:00
    ```

    **Timecodes with titles:**

    ```
    00:00:00:00-00:00:04:07|Segment 1: Introduction
    00:00:04:08-00:00:08:15|Segment 2: Main Content
    ```

    **JSON format:**

    ```json
    [
      {"start": "00:00:00:00", "end": "00:01:00:00", "title": "Intro"},
      {"start": "00:01:00:00", "end": "00:02:30:00", "title": "Main Content"}
    ]
    ```

### Outputs

- **split_videos**: List of split video segments (VideoUrlArtifact array)
- **logs**: Processing logs and detailed events

## Example

Imagine you want to split a 10-minute video into three segments:

1. Add a SplitVideo node to your workflow
1. Connect the video output from a LoadVideo node to the SplitVideo's "video" input
1. Enter timecodes in the "timecodes" parameter:
    ```
    00:00:00:00-00:02:30:00|Segment 1: Introduction
    00:02:30:00-00:07:30:00|Segment 2: Main Content
    00:07:30:00-00:10:00:00|Segment 3: Conclusion
    ```
1. Run the workflow - the video will be split into three separate files
1. Each segment will be available as a separate output in the split_videos list

## Important Notes

- The SplitVideo node uses AI-powered parsing to understand various timecode formats
- Timecodes should be in SMPTE format (HH:MM:SS:FF) where FF represents frames
- The node automatically detects video frame rate and drop frame settings
- Each segment maintains the original video quality and audio
- Processing time depends on video length and number of segments
- The node uses FFmpeg for high-quality video processing
- Logs provide detailed information about the splitting process

## Timecode Format Guidelines

- **Frame rates**: The node automatically detects 24fps, 25fps, 29.97fps, 30fps, 50fps, 59.94fps, and 60fps
- **Drop frame**: Automatically detected for 29.97fps and 59.94fps videos
- **Frame numbers**: Use 00-23 for 24fps, 00-24 for 25fps, 00-29 for 30fps, etc.
- **Separators**: Use hyphens (-) between start and end times, pipes (|) for titles
- **Titles**: Optional but recommended for better organization

## Common Issues

- **Invalid Timecodes**: Make sure timecodes are in correct SMPTE format (HH:MM:SS:FF)
- **Overlapping Segments**: Ensure segments don't overlap in time
- **Processing Timeout**: Large videos may take longer to process; the node has a 5-minute timeout
- **No Video Input**: Make sure a video source is connected to the "video" input
- **Empty Segments**: Check that start time is before end time for each segment
- **FFmpeg Errors**: Check the logs parameter for detailed error information if processing fails
