# ExtractAudio

## What is it?

The ExtractAudio node extracts the audio track from a video and outputs it as an audio file for use in your workflow. It supports multiple audio formats and quality settings, with options for both lossless copying and re-encoding.

## When would I use it?

Use the ExtractAudio node when:

- You need to separate audio from video content for audio processing workflows
- You want to convert video audio to different formats (MP3, WAV, AAC, etc.)
- You're creating audio-only content from video sources
- You need to extract audio for transcription, analysis, or editing
- You want to preserve the original audio quality by copying without re-encoding

## How to use it

### Basic Setup

1. Add an ExtractAudio node to your workflow
1. Connect a video input to the video parameter or manually select a video file
1. Choose your desired audio format and quality settings
1. Connect the extracted_audio output to other nodes that require audio input

### Parameters

#### Input

- **video**: The video content to extract audio from (supports VideoArtifact and VideoUrlArtifact)

#### Audio Settings

- **audio_format**: Output audio format

    - `mp3` (default) - Widely compatible, good compression
    - `wav` - Uncompressed, highest quality
    - `aac` - Good compression, modern standard
    - `flac` - Lossless compression
    - `ogg` - Open-source alternative with good compression
    - `m4a` - Apple's audio format, similar to AAC

- **audio_quality**: Audio quality/bitrate setting

    - `high` (128k) - High quality for most purposes (default)
    - `medium` (96k) - Balanced quality and file size
    - `low` (64k) - Smaller files, lower quality
    - `copy` - Copy original audio without re-encoding (fastest, preserves original quality)

### Outputs

- **extracted_audio**: The audio extracted from the video as an AudioUrlArtifact
- **logs**: Processing logs with detailed information about the extraction process

## Audio Format and Quality Guide

### Quality Settings

- **Copy**: Fastest option, preserves original audio quality and format exactly. Recommended when you don't need format conversion.
- **High (128k)**: Excellent quality for most use cases, good balance of quality and file size.
- **Medium (96k)**: Good quality for voice content, smaller file size.
- **Low (64k)**: Acceptable for voice-only content where file size is critical.

### Format Recommendations

- **MP3**: Most universally compatible, good for general use
- **WAV**: Use for highest quality or when working with audio editing software
- **AAC**: Modern standard with efficient compression, good for streaming
- **FLAC**: Use when you need lossless compression (smaller than WAV but larger than lossy formats)
- **OGG**: Open-source alternative to MP3, good compression
- **M4A**: Good for Apple ecosystem compatibility

## Example

Extracting audio from a video for transcription:

1. Add an ExtractAudio node to your workflow
1. Connect a video source to the **video** input
1. Set **audio_format** to `wav` for high compatibility with transcription services
1. Set **audio_quality** to `high` for best transcription accuracy
1. Connect the **extracted_audio** output to a transcription node
1. When the workflow runs, the audio will be extracted and available for transcription

## Performance Tips

- Use **copy** quality when you don't need to change the audio format - it's much faster
- Choose **MP3** with **high** quality for a good balance of quality, compatibility, and file size
- Use **WAV** format when working with audio editing software that requires uncompressed audio
- For long videos, the extraction process may take some time - check the logs for progress

## Important Notes

- **Audio Detection**: The node automatically detects if the video contains audio streams
- **No Audio Error**: If the input video has no audio track, the node will report an error
- **Format Support**: Supports all common video formats (mp4, avi, mov, mkv, webm, etc.)
- **Quality Preservation**: Using "copy" quality preserves the original audio exactly without any quality loss
- **Processing Speed**: Copy mode is fastest, while re-encoding takes longer but allows format conversion

## Common Issues

- **"No audio stream found"**: The input video doesn't contain any audio tracks. Check that your video file has audio.
- **Extraction Failed**: Make sure the input video is valid and accessible
- **Large File Processing**: For very large videos, extraction may take several minutes - monitor the logs for progress
- **Format Issues**: If you encounter format-specific issues, try using "copy" mode first to preserve the original audio format
