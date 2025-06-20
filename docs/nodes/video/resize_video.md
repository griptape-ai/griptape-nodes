# ResizeVideo

## What is it?

The ResizeVideo node allows you to resize video content by a specified percentage using FFmpeg. It can scale videos up or down while maintaining the original aspect ratio and ensuring compatibility with video codecs.

## When would I use it?

Use the ResizeVideo node when:

- You need to reduce video file size for storage or transmission
- You want to scale up videos for better quality on larger displays
- You need to standardize video dimensions across multiple files
- You want to optimize videos for specific platforms or devices
- You need to process videos to meet size or resolution requirements

## How to use it

### Basic Setup

1. Add a ResizeVideo node to your workflow
1. Connect a video source to the "video" input
1. Set the "percentage" parameter to your desired resize amount (1-400)
1. Choose a "scaling_algorithm" based on your quality and speed requirements
1. Run the workflow to resize the video

### Parameters

- **video**: The video content to resize (supports VideoArtifact and VideoUrlArtifact)

- **percentage**: The resize percentage as an integer (1-100, default: 50)

    - 50 = 50% of original size
    - 25 = 25% of original size (scaled down)
    - 200 = 200% of the original size (scaled up)

- **scaling_algorithm**: The algorithm used for video scaling (default: "bicubic")

    **Fast Algorithms (Lower Quality, Faster Processing):**

    - `fast_bilinear`: Very fast, basic quality - good for previews or quick processing
    - `bilinear`: Fast, decent quality - suitable for most general use cases
    - `neighbor`: Fastest, pixelated quality - useful for pixel art or retro effects

    **Balanced Algorithms (Good Quality, Moderate Speed):**

    - `bicubic`: High quality, good speed - recommended default choice
    - `area`: Good for downscaling, preserves details well
    - `bicublin`: Enhanced bicubic, slightly better quality than standard bicubic

    **High Quality Algorithms (Best Quality, Slower Processing):**

    - `lanczos`: Excellent quality, slower - best for professional work
    - `sinc`: Very high quality, very slow - for critical applications
    - `spline`: High quality, good for smooth scaling
    - `gauss`: High quality with Gaussian filtering

    **Specialized Algorithms:**

    - `experimental`: New algorithms, may vary in quality
    - `accurate_rnd`: Accurate rounding for precise dimensions
    - `full_chroma_int`: Full chroma interpolation
    - `full_chroma_inp`: Full chroma input
    - `bitexact`: Bit-exact processing for compatibility

- **lanczos_parameter**: Fine-tune the Lanczos scaling algorithm (1.0-10.0, default: 3.0)

    This parameter controls the alpha value for the Lanczos algorithm, affecting the sharpness and quality of the resized video:

    - **Lower values (2.0-3.0)**: Smoother results, less ringing artifacts
    - **Default (3.0)**: Balanced quality, good for most use cases
    - **Higher values (4.0-5.0)**: Sharper results, but may introduce ringing artifacts
    - **Very high values (6.0+)**: Maximum sharpness, but likely to have artifacts

    Only affects the output when `scaling_algorithm` is set to "lanczos".

### Outputs

- **resized_video**: The resized video content, available as output to connect to other nodes

## Example

Imagine you want to resize a large video file to 50% of its original size with high quality:

1. Add a ResizeVideo node to your workflow
1. Connect the video output from a LoadVideo node to the ResizeVideo's "video" input
1. Set the "percentage" parameter to 50
1. Choose "lanczos" as the scaling algorithm for best quality
1. Set the "lanczos_parameter" to 4.0 for sharper results (optional)
1. Run the workflow - the video will be resized to 50% of its original dimensions
1. The output filename will be `{original_filename}_resized_50_lanczos.{format}`

## Important Notes

- The ResizeVideo node uses FFmpeg for high-quality video processing
- Dimensions are automatically adjusted to be divisible by 2 for codec compatibility
- The original aspect ratio is preserved during resizing
- The node supports common video formats (mp4, avi, mov, etc.)
- Processing time depends on video size, complexity, and chosen scaling algorithm
- The resized video maintains the original audio track
- Logs are available for debugging processing issues

## Scaling Algorithm Recommendations

- **For general use**: Use `bicubic` (default) - good balance of quality and speed
- **For high-quality output**: Use `lanczos` or `sinc` - best quality but slower
    - With `lanczos`, try `lanczos_parameter` values of 3.0-4.0 for optimal results
- **For fast processing**: Use `bilinear` or `fast_bilinear` - faster but lower quality
- **For downscaling**: Use `area` - preserves details well when reducing size
- **For pixel art/retro**: Use `neighbor` - maintains sharp pixel boundaries

## Common Issues

- **Processing Timeout**: Large videos may take longer to process; the node has a 5-minute timeout
- **Invalid Percentage**: Make sure the percentage is between 1 and 100
- **Unsupported Format**: Check that your input video is in a supported format
- **No Video Input**: Make sure a video source is connected to the "video" input
- **FFmpeg Errors**: Check the logs parameter for detailed error information if processing fails
- **Slow Processing**: Consider using a faster scaling algorithm if processing is too slow
