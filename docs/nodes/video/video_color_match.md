# VideoColorMatch

## What is it?

The VideoColorMatch node transfers color characteristics from a reference image to a video using advanced color matching algorithms. By default, it uses a fast HALD CLUT (Color Lookup Table) method that applies the color transformation to the entire video in one pass, making it 10-50x faster than traditional frame-by-frame processing. This allows you to apply color grading to videos by matching the color palette of a reference image, useful for creating consistent visual styles, matching footage to a specific aesthetic, or applying cinematic color grading.

## When would I use it?

Use the VideoColorMatch node when:

- You want to apply color grading from a reference image to your video
- You need to match the color palette of multiple video clips for consistency
- You want to give your video a cinematic look based on a movie still or poster
- You're creating content that needs to match a specific aesthetic or mood
- You want to apply vintage or stylized color effects to modern footage
- You need to transfer the color characteristics from a photograph to video footage

## How to use it

### Basic Setup

1. Add a VideoColorMatch node to your workflow
1. Connect a reference image to "reference_image" (the image with the color palette you want to transfer)
1. Connect your video to "target_video" (the video you want to modify)
1. Select a color transfer method
1. Adjust the strength parameter to control the intensity
1. Run the workflow to apply the color transfer

### Parameters

#### Inputs

- **reference_image**: The reference image providing the color palette to transfer (supports ImageArtifact and ImageUrlArtifact)
- **target_video**: The video to apply color transfer to (supports VideoArtifact and VideoUrlArtifact)

#### Color Match Settings

- **transfer_method**: The processing method to use

    - **ffmpeg-haldclut**: Fast HALD CLUT-based transfer (10-50x faster, default) - Applies color matching once to a lookup table, then uses ffmpeg to process the entire video in one pass
    - **frame-by-frame**: Process each frame individually (slower, more memory intensive) - Extracts and processes each frame separately using the color-matcher library

- **method**: The color transfer algorithm to use

    - **mkl**: Monge-Kantorovich Linearization (fast, good quality, default)
    - **hm**: Histogram Matching (fast, moderate quality)
    - **reinhard**: Reinhard et al. color transfer (fast, good quality)
    - **mvgd**: Multi-Variate Gaussian Distribution (medium speed, good quality)
    - **hm-mvgd-hm**: Compound method (slower, best quality)
    - **hm-mkl-hm**: Alternative compound method (slower, best quality)

- **strength** (0.0-10.0, default: 1.0): Controls the intensity of the color transfer

    - 0.0 = no change (original video colors)
    - 1.0 = full color transfer (default)
    - Values > 1.0 exaggerate the effect

### Outputs

- **output**: The color-matched video with transferred color characteristics (VideoUrlArtifact)

The output video preserves:

- Original format (MP4, MOV, etc.)
- Original resolution and aspect ratio
- Original frame rate
- Original audio track (encoded as AAC at 192kbps)

## Example

### Basic Color Grading

Apply the color palette from a cinematic movie poster to your video:

1. Add a VideoColorMatch node to your workflow
1. Connect a LoadImage node with your reference movie poster to "reference_image"
1. Connect a LoadVideo node with your video to "target_video"
1. Keep the default "mkl" method
1. Set "strength" to 1.0 for full color transfer
1. Run the workflow - your video will match the color palette of the movie poster

### Subtle Vintage Effect

Apply a subtle vintage film look:

1. Load a vintage photograph as the reference image
1. Connect your modern video as the target
1. Set "method" to "reinhard" for natural luminance preservation
1. Set "strength" to 0.7 for a subtle effect
1. Run the workflow - the result will have a nostalgic vintage aesthetic

### Experimenting with Methods

Try different methods to see which aesthetic you prefer:

1. Process a short clip (2-3 seconds) with "mkl" method
1. Process the same clip with "hm-mvgd-hm" method
1. Compare the results to choose your preferred look
1. Apply to the full video

## Important Notes

- **Processing Time**:
    - **ffmpeg-haldclut (default)**: Very fast processing - a 10-second 1080p video at 30fps typically processes in seconds. Recommended for most use cases.
    - **frame-by-frame**: Slower processing - the same 10-second video may take 3-5 minutes. Useful if you need pixel-perfect control or encounter issues with the HALD CLUT method.
- **Progress Bar**:
    - **ffmpeg-haldclut**: Shows 10% for HALD generation, 20% for color matching, and 70% for video processing.
    - **frame-by-frame**: Shows 0-90% for frame processing and 90-100% for video reassembly.
- **Video Properties**: All original video properties (format, resolution, frame rate, duration) are preserved in the output.
- **Audio Preservation**: The original audio track is preserved (copied with ffmpeg-haldclut, re-encoded with AAC at 192kbps for frame-by-frame).
- **Memory Usage**: Both methods process efficiently - ffmpeg-haldclut streams through video, frame-by-frame processes sequentially.

## Algorithm Details

Different algorithms produce distinct aesthetic results:

- **mkl**: Fast optimal transport-based method. Good balance of speed and quality. Best for general use.
- **hm**: Matches color distributions using histograms. Can produce more dramatic color shifts.
- **reinhard**: Statistical color transfer that preserves luminance structure. Good for natural-looking results.
- **mvgd**: Models colors as Gaussian distributions. Better at capturing subtle color relationships.
- **hm-mvgd-hm**: Compound method applying histogram matching, then MVGD, then histogram matching again for refined results.
- **hm-mkl-hm**: Compound method using MKL as the middle step. Alternative approach for high-quality results.

## Tips and Best Practices

### Choosing a Reference Image

✓ **Good reference images:**

- Clear, well-exposed images with the desired color palette
- Images with similar lighting conditions to your video
- Reference images that represent the final look you want

✗ **Avoid:**

- Extremely dark or overexposed images
- Images with very different lighting scenarios than your video
- References with unnatural or oversaturated colors (unless that's your goal)

### Strength Guidelines

| Strength | Use Case                                             |
| -------- | ---------------------------------------------------- |
| 0.3-0.5  | Very subtle color correction, slight mood adjustment |
| 0.6-0.8  | Noticeable but natural color grading                 |
| 0.9-1.1  | Full color transfer, dramatic look change            |
| 1.2-2.0  | Stylized, artistic effects                           |
| > 2.0    | Experimental, heavily exaggerated results            |

### Transfer Method Selection

**When to use ffmpeg-haldclut (default):**

✓ For most use cases - it's fast and produces excellent results
✓ When processing longer videos or high-resolution footage
✓ When you want to preview results quickly
✓ For batch processing multiple videos

**When to use frame-by-frame:**

- If you encounter unexpected visual artifacts with HALD CLUT (rare)
- For troubleshooting or comparison purposes
- When you need to verify processing against the legacy method

### Workflow Recommendations

1. **Test with short clips first**: Process a 2-3 second clip before running on full videos to preview the effect
1. **Method comparison**: Try 2-3 different color methods with the same reference to see which aesthetic you prefer
1. **Batch processing**: Use the same reference image across multiple video clips for consistent look
1. **Strength refinement**: Start at 1.0, then adjust up or down based on results

## Common Issues

### Colors look too extreme

- **Solution**: Reduce "strength" to 0.6-0.8
- Or choose a less saturated reference image
- Or try "reinhard" method which preserves more original luminance

### Not enough color change

- **Solution**: Increase "strength" to 1.2-1.5
- Or choose a reference with more distinct colors
- Or try "hm-mvgd-hm" method for stronger transfer

### Processing takes too long

- **Solution**: Ensure you're using "ffmpeg-haldclut" transfer method (default, 10-50x faster)
- Or use "mkl" color method (fastest color transfer algorithm)
- Or pre-trim your video to the desired section using Split Video node
- Or reduce video resolution before processing using Resize Video node

### Output looks different than expected

- **Solution**: Try different color matching methods - each produces different results
- Ensure your reference image has the color characteristics you actually want
- Adjust strength to find the sweet spot for your specific content

## Performance Considerations

### HALD CLUT Method (Default - Recommended)

Processing time with **ffmpeg-haldclut** is very fast and depends primarily on:

- **Video length**: Scales linearly with duration
- **Resolution**: Higher resolutions take longer but still much faster than frame-by-frame
- **Color method**: All methods are fast since color matching happens once on the HALD CLUT

Approximate processing time for 1080p video at 30fps on modern hardware:

- 5 seconds: ~2-5 seconds
- 10 seconds: ~3-8 seconds
- 30 seconds: ~10-20 seconds
- 60 seconds: ~20-40 seconds

### Frame-by-Frame Method (Legacy)

Processing time with **frame-by-frame** depends on:

- **Video length**: Longer videos take proportionally longer to process
- **Resolution**: Higher resolution videos (4K vs 1080p) take significantly longer
- **Frame rate**: Higher frame rates mean more frames to process
- **Color method**: Compound methods (hm-mvgd-hm, hm-mkl-hm) take longer than simple methods (mkl, hm)

Approximate processing time for 1080p video at 30fps on modern hardware:

- 5 seconds (150 frames): ~1-2 minutes
- 10 seconds (300 frames): ~3-5 minutes
- 30 seconds (900 frames): ~8-12 minutes

## Related Nodes

- **Color Match** (Image category) - Single image color transfer, same algorithms
- **Adjust Video EQ** (Video category) - Manual brightness/contrast/saturation adjustments
- **Add Color Curves** (Video category) - Apply preset color grading curves to video

## Use Case Examples

### Cinematic Grading

- **Reference**: Movie still with teal/orange color grading
- **Method**: hm-mvgd-hm
- **Strength**: 0.9
- **Result**: Professional cinematic look with complementary color palette

### Vintage Film Effect

- **Reference**: 1970s photograph with warm, faded colors
- **Method**: reinhard
- **Strength**: 0.7
- **Result**: Nostalgic vintage aesthetic with authentic film look

### Day-to-Night Conversion

- **Reference**: Nighttime city photo with cool blue tones
- **Method**: mkl
- **Strength**: 1.2
- **Result**: Daytime video with nighttime color palette and mood

### Consistent Multi-Clip Grading

- **Reference**: Single color-graded frame from your best clip
- **Method**: mkl
- **Strength**: 1.0
- **Result**: All clips match the color palette for seamless editing
