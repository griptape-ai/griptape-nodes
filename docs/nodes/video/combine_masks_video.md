# CombineMasksVideo

## What is it?

The CombineMasksVideo node merges multiple mask videos into a single combined mask video by taking the pixel-wise maximum value across all input masks. It handles videos of different durations by padding shorter videos with black frames.

## When would I use it?

Use the CombineMasksVideo node when:

- You need to merge multiple mask videos into a single mask
- You want to combine object masks from different sources
- You're working with multiple segmentation outputs that need to be unified
- You need to create composite masks from multiple tracking results

## How to use it

### Basic Setup

1. Add a CombineMasksVideo node to your workflow
1. Connect mask video sources to the "mask_videos" input (accepts multiple videos as a list)
1. Run the workflow to combine the masks

### Parameters

- **mask_videos**: A list of mask videos to combine (supports VideoArtifact and VideoUrlArtifact)

### Outputs

- **combined_mask**: The combined mask video, available as output to connect to other nodes

## How it works

The node processes videos frame-by-frame using a pixel-wise maximum operation:

- Each frame is converted to grayscale (if not already)
- For each pixel position, the maximum value across all input masks is selected
- The result is a mask where any white pixel from any input mask appears white in the output
- If input videos have different durations, shorter videos are padded with black frames to match the longest video

A progress indicator shows processing status (0-90% for frame processing, 90-100% for video reassembly).

## Example

To combine two mask videos tracking different objects:

1. Connect both mask videos to the **mask_videos** input
1. Run the workflow
1. The output will contain white pixels wherever either input mask had white pixels

## Important Notes

- The CombineMasksVideo node uses FFmpeg for video processing
- All input masks are converted to grayscale during processing
- The output video resolution matches the first input video
- Videos with different durations are automatically handled through black frame padding
- The output video maintains the frame rate of the reference (first) video
- Logs are available for debugging processing issues
