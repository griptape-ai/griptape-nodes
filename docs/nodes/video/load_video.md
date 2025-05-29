# LoadVideo

## What is it?

The LoadVideo is a simple building block that lets you bring a video into your workflow. Think of it as picking up a video file so you can use it in your project.

## When would I use it?

Use this node when you want to:

- Use a video that was created by another node
- Pass a video to other nodes in your workflow
- Display a video as part of your project
- Load video files from disk into your workflow

## How to use it

### Basic Setup

1. Add the LoadVideo to your workflow
1. Connect it to a source of videos or use the file browser to select a video file

### Parameters

- **video**: The video to load (this can be connected to an output from another node or loaded from a file)

### Outputs

- **video**: The loaded video that can be used by other nodes in your flow

## Example

Imagine you want to load a video file from your computer:

1. Add a LoadVideo node to your workflow
1. Click the file browser icon to select a video file from your computer
1. The LoadVideo will make the video available to use in the rest of your workflow

## Important Notes

- The LoadVideo simply passes the video through - it doesn't change the video itself
- You can click the file browser icon to select a video from your computer
- The video preview can be expanded by clicking the expander icon
- Supports common video formats (mp4, avi, mov, etc.)

## Common Issues

- **No Video Showing**: Make sure you've properly connected a video source to this node or selected a file
- **Unsupported Format**: Check that your video file is in a supported format
