# AddRGBShift

## What is it?

The AddRGBShift node adds RGB shift (chromatic aberration) effects to video, creating visual distortions where the red, green, and blue color channels are offset from each other. It can create both static and animated glitch effects with VHS-style artifacts.

## When would I use it?

Use the AddRGBShift node when:

- You want to create glitch art or digital distortion effects
- You need to simulate VHS tape artifacts and degradation
- You're creating cyberpunk or retro-futuristic content
- You want to add visual interest to otherwise clean footage
- You need to create unsettling or disorienting visual effects
- You're making content that mimics old video technology

## How to use it

### Basic Setup

1. Add an AddRGBShift node to your workflow
1. Connect a video source to the "video" input
1. Choose between "static" or "animated" glitch mode
1. Adjust the RGB shift parameters and visual effects
1. Run the workflow to add the RGB shift effect

### Parameters

#### Glitched Visual Style

- **red_horizontal**: Red channel horizontal shift (-20 to 20 pixels, default: -6)
- **red_vertical**: Red channel vertical shift (-20 to 20 pixels, default: 0)
- **green_horizontal**: Green channel horizontal shift (-20 to 20 pixels, default: 6)
- **green_vertical**: Green channel vertical shift (-20 to 20 pixels, default: 0)
- **blue_horizontal**: Blue channel horizontal shift (-20 to 20 pixels, default: 0)
- **blue_vertical**: Blue channel vertical shift (-20 to 20 pixels, default: 0)
- **intensity**: Overall intensity of the RGB shift effect (0.0-1.0, default: 1.0)

#### Glitch Animation Settings

- **glitch_frequency**: Number of glitches per second when animated (0.1-10.0, default: 2.0)
- **glitch_duration**: Duration of each glitch in seconds (0.01-0.5, default: 0.1)
- **glitch_intensity**: Intensity of glitch shifts when animated (0.0-1.0, default: 0.5)

#### Tear Effects

- **tear_offset_min**: Minimum horizontal offset for tear effect (-50 to 50 pixels, default: 5)
- **tear_offset_max**: Maximum horizontal offset for tear effect (-50 to 50 pixels, default: 15)

#### Random Seed Settings

- **random_seed**: Random seed for glitch timing (default: 42, use -1 for random patterns)

#### Non-Glitched Visual Style (VHS Base Effects)

- **noise_strength**: Tape noise strength (0-50, default: 8)
- **chroma_shift_horizontal**: Chroma shift horizontal (always active) (-10 to 10 pixels, default: 2)
- **chroma_shift_vertical**: Chroma shift vertical (always active) (-10 to 10 pixels, default: -2)
- **blur_strength**: Blur strength (0.0-3.0, default: 0.8)
- **motion_trails**: Motion trail frames (1-5, default: 3)

### Outputs

- **video**: The video with RGB shift effects added, available as output to connect to other nodes

## Example

Imagine you want to create a VHS-style glitch effect on a video:

1. Add an AddRGBShift node to your workflow
1. Connect the video output from a LoadVideo node to the AddRGBShift's "video" input
1. Set glitch_mode to "animated" for dynamic effects
1. Set red_horizontal to -8, green_horizontal to 8 for classic RGB separation
1. Set glitch_frequency to 1.5 for moderate glitch timing
1. Set noise_strength to 12 for visible tape noise
1. Run the workflow - the video will have VHS-style glitch effects
1. The output filename will include all the effect parameters

## Important Notes

- The AddRGBShift node uses FFmpeg with complex filter chains for realistic effects
- Animated mode creates sporadic, unpredictable glitches with random timing
- Static mode applies constant RGB shift throughout the video
- Tear effects randomly occur during animated glitches
- The original audio track is preserved
- Processing time depends on video length and effect complexity

## Effect Recommendations

- **Subtle RGB shift**: Use small values (2-4 pixels) for red/green horizontal shifts
- **Heavy glitch effect**: Use larger values (10-20 pixels) and animated mode
- **VHS simulation**: Combine noise_strength 8-15, chroma_shift, and blur_strength 0.5-1.0
- **Cyberpunk aesthetic**: Use animated mode with high glitch_frequency and tear effects
- **Retro video look**: Use static mode with moderate RGB shifts and noise

## Common Issues

- **Processing Timeout**: Complex effects may take longer to process; the node has a 5-minute timeout
- **Effect Too Strong**: Reduce intensity or RGB shift values if the effect is overwhelming
- **No Glitches in Animated Mode**: Check glitch_frequency and ensure random_seed is set appropriately
- **No Video Input**: Make sure a video source is connected to the "video" input
- **FFmpeg Errors**: Check the logs parameter for detailed error information if processing fails
