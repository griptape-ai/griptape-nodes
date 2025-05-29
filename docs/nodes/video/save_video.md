# SaveVideo

## What is it?

The SaveVideo node allows you to save video content from your workflow to a file on your computer.

## When would I use it?

Use the SaveVideo node when:

- You want to export video results from your workflow
- You need to save processed video content to disk
- You want to create video files that can be used outside of your workflow
- You need to archive video outputs for later use

## How to use it

### Basic Setup

1. Add a SaveVideo node to your workflow
1. Connect a video source to the "video" input
1. Optionally specify the output filename and path
1. Run the workflow to save the video file

### Parameters

- **video**: The video content to save (supports VideoArtifact, VideoUrlArtifact, and dict)
- **output_path**: The filename and path where the video should be saved (default: "griptape_nodes.mp4")

### Outputs

- **output_path**: The path where the video was saved

## Example

Imagine you want to save a video that was processed in your workflow:

1. Add a SaveVideo node to your workflow
1. Connect the video output from another node to the SaveVideo's "video" input
1. Set the "output_path" to your desired filename (e.g., "my_video.mp4")
1. Run the workflow - the video will be saved to the specified location

## Important Notes

- The SaveVideo node supports common video formats (.mp4, .avi, .mov, etc.)
- The output path can include a directory structure (e.g., "videos/output.mp4")
- If no extension is provided, .mp4 will be used by default
- The node will create directories if they don't exist
- You can use the save button in the UI to browse for a save location

## Common Issues

- **Permission Denied**: Make sure you have write permissions to the specified directory
- **Invalid Path**: Check that the output path is valid and the directory exists
- **Unsupported Format**: Ensure you're using a supported video file extension
- **No Video Input**: Make sure a video source is connected to the "video" input
