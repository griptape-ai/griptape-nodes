# AdjustVideoEQ

## What is it?

The AdjustVideoEQ node allows you to adjust video brightness, contrast, saturation, and gamma settings. It provides precise control over the visual appearance of your video content using FFmpeg's high-quality equalization filters.

## When would I use it?

Use the AdjustVideoEQ node when:

- You need to correct exposure issues in your video
- You want to enhance the visual quality of poorly lit footage
- You need to adjust color saturation for artistic or technical reasons
- You want to match the look of multiple video clips
- You're creating content that needs specific visual adjustments
- You want to improve the overall visual appeal of your video

## How to use it

### Basic Setup

1. Add an AdjustVideoEQ node to your workflow
1. Connect a video source to the "video" input
1. Adjust the brightness, contrast, saturation, and gamma parameters
1. Run the workflow to apply the EQ adjustments

### Parameters

- **video**: The video content to adjust (supports VideoArtifact and VideoUrlArtifact)

- **brightness**: Brightness adjustment (-1.0 to 1.0, default: 0.0)

    - -1.0 = very dark
    - 0.0 = normal brightness (default)
    - 1.0 = very bright

- **contrast**: Contrast adjustment (0.0 to 3.0, default: 1.0)

    - 0.0 = no contrast (flat image)
    - 1.0 = normal contrast (default)
    - 3.0 = very high contrast

- **saturation**: Saturation adjustment (0.0 to 3.0, default: 1.0)

    - 0.0 = black and white
    - 1.0 = normal saturation (default)
    - 3.0 = very saturated colors

- **gamma**: Gamma adjustment (0.1 to 10.0, default: 1.0)

    - 0.1 = very bright mid-tones
    - 1.0 = normal gamma (default)
    - 10.0 = very dark mid-tones

- **processing_speed**: Balance between processing speed and output quality (default: "balanced")

    - **fast**: Fastest processing, lower quality (ultrafast preset, CRF 30)
    - **balanced**: Good balance of speed and quality (medium preset, CRF 23)
    - **quality**: Highest quality, slower processing (slow preset, CRF 18)

### Outputs

- **video**: The video with EQ adjustments applied, available as output to connect to other nodes

## Example

Imagine you want to brighten a dark video and increase its saturation:

1. Add an AdjustVideoEQ node to your workflow
1. Connect the video output from a LoadVideo node to the AdjustVideoEQ's "video" input
1. Set "brightness" to 0.3 to brighten the video
1. Set "contrast" to 1.2 to enhance contrast
1. Set "saturation" to 1.5 to make colors more vibrant
1. Keep "gamma" at 1.0 for normal mid-tone response
1. Run the workflow - the video will be brighter and more saturated
1. The output filename will be `{original_filename}_eq_b0.30_c1.20_s1.50_g1.00.{format}`

## Important Notes

- The AdjustVideoEQ node uses FFmpeg with high-quality equalization algorithms
- All parameters work together to create the final visual effect
- The original audio track is preserved
- Processing time depends on video length and resolution
- Logs are available for debugging processing issues

## Parameter Recommendations

- **For dark footage**: Use brightness 0.2-0.5, contrast 1.1-1.3
- **For overexposed footage**: Use brightness -0.2 to -0.5, contrast 0.8-0.9
- **For flat footage**: Use contrast 1.2-1.5, saturation 1.1-1.3
- **For vibrant colors**: Use saturation 1.3-1.8, gamma 0.9-1.1
- **For cinematic look**: Use contrast 1.1-1.2, saturation 0.8-0.9, gamma 1.1-1.2
- **For vintage effect**: Use saturation 0.7-0.8, gamma 1.2-1.4

## Common Issues

- **Processing Timeout**: Large videos may take longer to process; the node has a 5-minute timeout
- **Too Bright/Dark**: Adjust brightness value - use negative values to darken, positive to brighten
- **Colors Too Saturated**: Reduce saturation value below 1.0
- **No Video Input**: Make sure a video source is connected to the "video" input
- **FFmpeg Errors**: Check the logs parameter for detailed error information if processing fails
