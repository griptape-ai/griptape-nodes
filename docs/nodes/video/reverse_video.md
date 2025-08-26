# ReverseVideo

## What is it?

The ReverseVideo node reverses the playback direction of your video, making it play backwards. It can also handle audio reversal or muting depending on your needs.

## When would I use it?

Use the ReverseVideo node when:

- You want to create backwards playback effects
- You need to reverse footage for artistic or creative purposes
- You're creating special effects that require reverse motion
- You want to add surreal or dreamlike qualities to your video
- You need to reverse specific segments for editing purposes
- You're making content that requires backwards motion analysis

## How to use it

### Basic Setup

1. Add a ReverseVideo node to your workflow
1. Connect a video source to the "video" input
1. Choose how to handle audio (reverse, mute, or keep original)
1. Run the workflow to reverse the video

### Parameters

- **video**: The video content to reverse (supports VideoArtifact and VideoUrlArtifact)

- **audio_handling**: How to handle audio (default: "reverse")

    - "reverse" = reverse both video and audio (recommended)
    - "mute" = reverse video only, no audio
    - "keep" = reverse video, keep original audio (not recommended)

- **processing_speed**: Balance between processing speed and output quality (default: "balanced")

    - **fast**: Fastest processing, lower quality (ultrafast preset, CRF 30)
    - **balanced**: Good balance of speed and quality (medium preset, CRF 23)
    - **quality**: Highest quality, slower processing (slow preset, CRF 18)

### Outputs

- **video**: The reversed video, available as output to connect to other nodes

## Example

Imagine you want to create a backwards playback effect:

1. Add a ReverseVideo node to your workflow
1. Connect the video output from a LoadVideo node to the ReverseVideo's "video" input
1. Set "audio_handling" to "reverse" to reverse both video and audio
1. Run the workflow - the video will play backwards
1. The output filename will be `{original_filename}_reversed_reverse.{format}`

## Important Notes

- The ReverseVideo node uses FFmpeg with high-quality reverse processing
- Reversing both video and audio creates the most natural backwards effect
- Muting audio is recommended if you want to avoid strange backwards audio
- The "keep" option may create audio sync issues
- Processing time depends on video length
- Logs are available for debugging processing issues
- The node automatically detects if the video has audio and handles it appropriately
- Videos without audio will be processed correctly without errors

## Audio Handling Recommendations

- **For natural backwards effect**: Use "reverse" - both video and audio play backwards
- **For silent backwards effect**: Use "mute" - video plays backwards with no audio
- **For custom audio**: Use "mute" and add your own audio track separately

## Common Issues

- **Processing Timeout**: Large videos may take longer to process; the node has a 5-minute timeout
- **Strange Audio**: If audio sounds odd, try using "mute" instead of "reverse"
- **Audio Sync Issues**: The "keep" option may cause audio/video synchronization problems
- **No Video Input**: Make sure a video source is connected to the "video" input
- **FFmpeg Errors**: Check the logs parameter for detailed error information if processing fails
