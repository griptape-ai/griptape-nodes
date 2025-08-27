# ExtractLastFrame

## What is it?

The ExtractLastFrame node extaracts the last frame from a video as an image for use in your workflow.

## When would I use it?

Use the ExtractLastFrame node when:

- You need to extract the final frame from a video for use in your worflow. 

## How to use it

### Basic Setup

1. Add a ExtractLastFrame node to your workflow
1. Connect an input to the video parameter or manually select a video
1. Connect the last_frame_image output to other nodes that require image input

### Parameters

- **video**: The video content to extract the last frame from (supports VideoArtifact and VideoUrlArtifact)

### Outputs

- **last_frame_image**: The the last frame from the video, output as an ImageUrlArtifact

## Example

When working with image to video models you might want to chain several short video clips together to make one longer video.

1. Add a ExtractLastFrame node to your workflow
1. Connect the ouput from an image to video node to the **video** input on the ExtractLastFrame node
1. When the ExtractLastFrame node or workflow runs, the last frame from the video will be displayed in the node

## Important Notes

- Supports common video formats (mp4, avi, mov, etc.)
- The video player controls allow you to play, pause, and scrub through the video

## Common Issues

- **No Video Showing**: Make sure you've properly connected a video source to this node
