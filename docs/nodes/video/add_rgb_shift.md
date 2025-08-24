# AddRGBShift

## What is it?

The AddRGBShift node adds RGB shift (chromatic aberration) effects to video, creating visual distortions where the red, green, and blue color channels are offset from each other. It can also add a tear effect that splits the video horizontally and applies different RGB shifts to each part.

## When would I use it?

Use the AddRGBShift node when:

- You want to create glitch art or digital distortion effects
- You need to simulate chromatic aberration or lens distortion
- You're creating cyberpunk or retro-futuristic content
- You want to add visual interest to otherwise clean footage
- You need to create unsettling or disorienting visual effects
- You want to add a tear effect that splits the video horizontally

## How to use it

### Basic Setup

1. Add an AddRGBShift node to your workflow
1. Connect a video source to the "video" input
1. Adjust the RGB shift parameters for each color channel
1. Optionally enable the tear effect and configure its position and offset
1. Run the workflow to add the RGB shift effect

### Parameters

#### RGB Shift Settings

- **red_horizontal**: Red channel horizontal shift (-20 to 20 pixels, default: -6)
- **red_vertical**: Red channel vertical shift (-20 to 20 pixels, default: 0)
- **green_horizontal**: Green channel horizontal shift (-20 to 20 pixels, default: 6)
- **green_vertical**: Green channel vertical shift (-20 to 20 pixels, default: 0)
- **blue_horizontal**: Blue channel horizontal shift (-20 to 20 pixels, default: 0)
- **blue_vertical**: Blue channel vertical shift (-20 to 20 pixels, default: 0)
- **intensity**: Overall intensity of the RGB shift effect (0.0-1.0, default: 1.0)

#### Tear Effect Settings

- **tear_enabled**: Enable tear effect (default: False)
- **tear_position**: Vertical position of tear (0.0-1.0, where 0.5 is center, default: 0.5)
- **tear_offset**: Horizontal offset amount for tear effect (-50 to 50 pixels, default: 10)

### Outputs

- **video**: The video with RGB shift effects added, available as output to connect to other nodes

## Example

Imagine you want to create a glitch effect on a video:

1. Add an AddRGBShift node to your workflow
1. Connect the video output from a LoadVideo node to the AddRGBShift's "video" input
1. Set red_horizontal to -8, green_horizontal to 8 for classic RGB separation
1. Set intensity to 0.8 for a moderate effect
1. Enable tear_enabled and set tear_position to 0.6 and tear_offset to 15
1. Run the workflow - the video will have RGB shift effects with a tear at 60% down the frame
1. The output filename will include all the effect parameters

## Important Notes

- The AddRGBShift node uses FFmpeg with the rgbashift filter for reliable effects
- The tear effect splits the video horizontally and applies different RGB shifts to each part
- The original audio track is preserved
- Processing time depends on video length and effect complexity

## Effect Recommendations

- **Subtle RGB shift**: Use small values (2-4 pixels) for red/green horizontal shifts
- **Heavy glitch effect**: Use larger values (10-20 pixels) for dramatic separation
- **Tear effect**: Position the tear at 0.3-0.7 for best visual impact
- **Cyberpunk aesthetic**: Combine red/green horizontal shifts with tear effects
- **Retro video look**: Use moderate RGB shifts with intensity around 0.7-0.9

## Common Issues

- **Processing Timeout**: Complex effects may take longer to process; the node has a 5-minute timeout
- **Effect Too Strong**: Reduce intensity or RGB shift values if the effect is overwhelming
- **No Video Input**: Make sure a video source is connected to the "video" input
- **FFmpeg Errors**: Check the logs parameter for detailed error information if processing fails
