# AddFilmGrain

## What is it?

The AddFilmGrain node adds realistic film grain to video using sophisticated noise generation and luminance masking. It creates authentic film-like texture that varies based on the brightness of different areas in the video.

## When would I use it?

Use the AddFilmGrain node when:

- You want to add a cinematic, film-like quality to digital video
- You need to create vintage or retro video effects
- You want to add texture and character to clean digital footage
- You're creating content that needs to look like it was shot on film
- You want to enhance the visual depth and atmosphere of your video

## How to use it

### Basic Setup

1. Add an AddFilmGrain node to your workflow
1. Connect a video source to the "video" input
1. Adjust the grain intensity, luminance threshold, and grain scale parameters
1. Run the workflow to add film grain to your video

### Parameters

- **video**: The video content to add film grain to (supports VideoArtifact and VideoUrlArtifact)

- **grain_intensity**: Film grain intensity (0.05-1.0, default: 0.15)

    - 0.05 = very subtle grain
    - 0.15 = moderate grain (default)
    - 0.5 = heavy grain
    - 1.0 = maximum grain intensity

- **luminance_threshold**: Luminance level where grain is most visible (50-100, default: 75)

    - 50 = grain visible in darker areas
    - 75 = grain visible in mid-tones (default, good for faces)
    - 100 = grain visible in brighter areas

- **grain_scale**: Grain scale factor (1.0-4.0, default: 2.0)

    - 1.0 = fine grain particles
    - 2.0 = medium grain (default)
    - 4.0 = larger grain particles

### Outputs

- **video**: The video with film grain added, available as output to connect to other nodes

## Example

Imagine you want to add a subtle film grain to a digital video to give it a cinematic look:

1. Add an AddFilmGrain node to your workflow
1. Connect the video output from a LoadVideo node to the AddFilmGrain's "video" input
1. Set the "grain_intensity" to 0.12 for subtle grain
1. Set the "luminance_threshold" to 75 for optimal grain visibility on faces
1. Set the "grain_scale" to 2.0 for medium-sized grain particles
1. Run the workflow - the video will have realistic film grain added
1. The output filename will be `{original_filename}_grain_0.12.{format}`

## Important Notes

- The AddFilmGrain node uses FFmpeg with sophisticated noise generation algorithms
- Grain intensity is automatically adjusted based on the luminance of each pixel
- The effect creates temporal grain that changes between frames for realism
- Processing time depends on video length and resolution
- The original audio track is preserved
- Logs are available for debugging processing issues

## Parameter Recommendations

- **For subtle film look**: Use grain_intensity 0.08-0.15, luminance_threshold 75
- **For vintage/retro effect**: Use grain_intensity 0.3-0.6, grain_scale 2.5-3.0
- **For heavy film grain**: Use grain_intensity 0.7-1.0, grain_scale 3.0-4.0
- **For portraits**: Use luminance_threshold 70-80 for optimal grain on faces
- **For landscapes**: Use luminance_threshold 60-70 for grain in mid-tones

## Common Issues

- **Processing Timeout**: Large videos may take longer to process; the node has a 5-minute timeout
- **Too Much Grain**: Reduce grain_intensity if the effect is too strong
- **Grain Not Visible**: Increase grain_intensity or adjust luminance_threshold
- **No Video Input**: Make sure a video source is connected to the "video" input
- **FFmpeg Errors**: Check the logs parameter for detailed error information if processing fails
