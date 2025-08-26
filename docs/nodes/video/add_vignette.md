# AddVignette

## What is it?

The AddVignette node adds a vignette effect to video, creating a gradual darkening or lightening around the edges of the frame. This effect can enhance the visual focus on the center of the frame and add a cinematic quality to your video.

## When would I use it?

Use the AddVignette node when:

- You want to draw attention to the center of your video frame
- You need to create a cinematic, film-like look
- You want to add depth and atmosphere to your video
- You're creating content that needs a professional, polished appearance
- You want to simulate the natural light falloff of camera lenses
- You need to enhance the mood or emotional impact of your video

## How to use it

### Basic Setup

1. Add an AddVignette node to your workflow
1. Connect a video source to the "video" input
1. Adjust the vignette angle, center position, and aspect ratio
1. Choose between "forward" (darken edges) or "backward" (lighten edges) mode
1. Run the workflow to add the vignette effect

### Parameters

- **video**: The video content to add vignette to (supports VideoArtifact and VideoUrlArtifact)

- **angle**: Lens angle for vignette effect (0.1-3.14, default: 0.628)

    - Smaller values = less vignette effect
    - 0.1 = very subtle vignette
    - 0.628 = moderate vignette (default)
    - 3.14 = very strong vignette

- **center_x**: Center X offset (-1.0 to 1.0, default: 0.0)

    - -1.0 = far left
    - 0.0 = center (default)
    - 1.0 = far right

- **center_y**: Center Y offset (-1.0 to 1.0, default: 0.0)

    - -1.0 = top
    - 0.0 = center (default)
    - 1.0 = bottom

- **aspect**: Aspect ratio of vignette (0.1-10.0, default: 1.0)

    - 0.1 = very wide vignette
    - 1.0 = circular vignette (default)
    - 10.0 = very tall vignette

- **mode**: Vignette mode (default: "forward")

    - "forward" = darken edges (traditional vignette)
    - "backward" = lighten edges (inverse vignette)

- **processing_speed**: Balance between processing speed and output quality (default: "balanced")

    - **fast**: Fastest processing, lower quality (ultrafast preset, CRF 30)
    - **balanced**: Good balance of speed and quality (medium preset, CRF 23)
    - **quality**: Highest quality, slower processing (slow preset, CRF 18)

### Outputs

- **video**: The video with vignette effect added, available as output to connect to other nodes

## Example

Imagine you want to add a subtle vignette to a portrait video to draw attention to the subject:

1. Add an AddVignette node to your workflow

1. Connect the video output from a LoadVideo node to the AddVignette's "video" input

1. Set the "angle" to 0.5 for a moderate vignette effect

1. Keep "center_x" and "center_y" at 0.0 to center the vignette

1. Set "aspect" to 1.0 for a circular vignette

1. Choose "forward" mode to darken the edges

1. Run the workflow - the video will have a subtle vignette effect

1. The output filename will be `{original_filename}_vignette_a0.50_x0.00_y0.00_r1.00_forward.{format}`

## Important Notes

- The AddVignette node uses FFmpeg with high-quality vignette algorithms
- The effect creates smooth, gradual transitions from center to edges
- The original audio track is preserved
- Processing time depends on video length and resolution
- Logs are available for debugging processing issues

## Parameter Recommendations

- **For portraits**: Use angle 0.4-0.6, center at (0,0), aspect 1.0
- **For landscapes**: Use angle 0.3-0.5, center at (0,0), aspect 1.5-2.0
- **For cinematic look**: Use angle 0.5-0.8, forward mode
- **For subtle enhancement**: Use angle 0.8-1.2 for very gentle vignette
- **For dramatic effect**: Use angle 2.0-3.0 for strong vignette
- **For off-center subjects**: Adjust center_x and center_y to match subject position

## Common Issues

- **Processing Timeout**: Large videos may take longer to process; the node has a 5-minute timeout
- **Vignette Too Strong**: Decrease the angle value to make the effect more subtle
- **Vignette Not Visible**: Increase the angle value to make the effect stronger
- **No Video Input**: Make sure a video source is connected to the "video" input
- **FFmpeg Errors**: Check the logs parameter for detailed error information if processing fails
