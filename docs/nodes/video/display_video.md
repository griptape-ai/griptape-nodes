# DisplayVideo

## What is it?

The DisplayVideo node simply displays video content in your workflow.

## When would I use it?

Use the DisplayVideo node when:

- You need to display video results or information in your workflow
- You want to show video output from previous processing steps
- You need a placeholder for video content that will be updated during workflow execution
- You want to create readable labels or descriptions within your workflow
- You need to visualize video data at specific points in your process

## How to use it

### Basic Setup

1. Add a DisplayVideo node to your workflow
1. Set the initial video value if desired
1. Connect inputs to the video parameter or manually select a video
1. Connect the video output to other nodes that require video input

### Parameters

- **video**: The video content to display (supports VideoArtifact and VideoUrlArtifact)

### Outputs

- **video**: The same video content, available as output to connect to other nodes

## Example

Imagine you're building a workflow that processes and displays video information:

1. Add a DisplayVideo node to your workflow
1. Connect the output from a LoadVideo node to the DisplayVideo node's video parameter
1. When the workflow runs, the video content will be displayed in the node

## Important Notes

- The DisplayVideo node is for visualization and doesn't modify the video content
- The node passes through video exactly as received, without any processing or formatting
- Supports common video formats (mp4, avi, mov, etc.)
- The video player controls allow you to play, pause, and scrub through the video

## Common Issues

- **No Video Showing**: Make sure you've properly connected a video source to this node
- **Video Won't Play**: Check that your video file is in a supported format and not corrupted
