# CompareImages

## What is it?

The CompareImages node allows you to compare two images side by side, making it easy to see differences, evaluate changes, or compare different versions of the same image. It's perfect for A/B testing, quality control, or analyzing the effects of different image processing operations.

## When would I use it?

Use this node when you want to:

- Compare before and after versions of processed images
- A/B test different image generation prompts
- Evaluate the quality of different image processing settings
- Compare different versions of the same image
- Analyze the effects of image adjustments
- Quality control for image processing workflows
- Present multiple image options for review

## How to use it

### Basic Setup

1. Add the CompareImages node to your workflow
1. Connect two image sources to the "image1" and "image2" inputs
1. The comparison will be displayed showing both images side by side

### Parameters

- **image1**: The first image to compare (left side)
- **image2**: The second image to compare (right side)

### Outputs

- **comparison**: A side-by-side comparison of both images

## Example

A typical comparison workflow:

1. Load an original image using LoadImage
1. Process the image with AdjustImageEQ or another processing node
1. Connect the original image to CompareImages "image1" input
1. Connect the processed image to CompareImages "image2" input
1. The node will display both images side by side for easy comparison

## Important Notes

- **Side-by-Side Display**: Images are displayed next to each other for easy comparison
- **Automatic Scaling**: Images are automatically scaled to fit the comparison view
- **Real-time Updates**: The comparison updates when either input image changes
- **High Quality**: Maintains image quality for accurate comparison

## Common Issues

- **No Images Showing**: Make sure both image1 and image2 inputs are connected
- **Images Too Small**: The node automatically scales images to fit the display
- **Layout Issues**: The side-by-side layout is automatic and optimized for comparison

## Technical Details

The node creates a composite image that displays both input images side by side, making it easy to:

- Compare image quality
- See processing effects
- Evaluate different versions
- Make informed decisions about image processing

This is essential for any workflow that involves image processing or generation where you need to evaluate results.
