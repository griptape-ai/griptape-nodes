# AdjustMaskSize

## What is it?

The AdjustMaskSize node adjusts the size of masks in a video by dilating (expanding) or eroding (shrinking) the mask boundaries. It processes each frame individually using morphological operations while maintaining video properties.

## When would I use it?

Use the AdjustMaskSize node when:

- You need to expand mask boundaries to include more surrounding area (dilation)
- You want to shrink masks to remove edge artifacts or thin borders (erosion)
- You need to refine mask edges from segmentation or tracking results
- You want to adjust mask coverage by a precise number of pixels

## How to use it

### Basic Setup

1. Add an AdjustMaskSize node to your workflow
1. Connect a mask video source to the "mask_video" input
1. Adjust the "adjustment" slider to set the desired expansion or shrinkage
1. Run the workflow to process the mask video

### Parameters

- **mask_video**: The mask video to adjust (supports VideoArtifact and VideoUrlArtifact)

- **adjustment**: Mask size adjustment in pixels (-25 to +25, default: 0)

    - Positive values (1 to 25): Expand the mask (dilation)
    - Negative values (-25 to -1): Shrink the mask (erosion)
    - Zero (0): Pass through unchanged (no processing)

### Outputs

- **output_mask**: The adjusted mask video, available as output to connect to other nodes

## How it works

The node applies morphological operations frame-by-frame:

- **Dilation (positive adjustment)**: Expands white regions in the mask by applying a maximum filter. Each white pixel expands outward by the specified number of pixels using a circular kernel.

- **Erosion (negative adjustment)**: Shrinks white regions in the mask by applying a minimum filter. Each white pixel shrinks inward by the specified number of pixels using a circular kernel.

- **Zero adjustment**: When adjustment is 0, the input video is returned unchanged without processing.

The circular kernel ensures natural-looking, uniform expansion or contraction in all directions. A progress indicator shows processing status (0-90% for frame processing, 90-100% for video reassembly).

## Example

To expand a mask by 5 pixels to include more surrounding area:

1. Connect your mask video to the **mask_video** input
1. Set **adjustment** to `5`
1. Run the workflow
1. The output mask will have boundaries expanded by 5 pixels in all directions

To remove a 3-pixel border from a mask:

1. Connect your mask video to the **mask_video** input
1. Set **adjustment** to `-3`
1. Run the workflow
1. The output mask will have boundaries shrunk by 3 pixels in all directions

## Important Notes

- The AdjustMaskSize node uses FFmpeg for video frame extraction and reassembly
- Morphological operations use PIL (Pillow) MaxFilter and MinFilter for efficient processing
- The circular kernel provides smooth, natural-looking results
- Input masks are automatically converted to grayscale during processing
- The output video maintains the same resolution, frame rate, and duration as the input
- Zero adjustment skips all processing for efficiency
- Logs are available for debugging processing issues
