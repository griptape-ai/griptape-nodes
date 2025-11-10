# ExtractKeyColors

## What is it?

The ExtractKeyColors node analyzes images and extracts the most prominent colors using either KMeans clustering or Median Cut (MMCQ) algorithms. It automatically orders colors by their frequency in the image and creates dynamic color picker parameters for each extracted color, making it perfect for color palette generation, brand analysis, and design workflows.

## When would I use it?

Use this node when you want to:

- Generate color palettes from images for design projects
- Analyze dominant colors in logos and marketing materials
- Extract brand colors from images
- Create color schemes based on image content
- Build color-based filters and effects
- Generate color data for visualization projects
- Analyze color distribution in photographs
- Create design systems from visual references

## How to use it

### Basic Setup

1. Add the ExtractKeyColors node to your workflow
1. Connect an image source to the "input_image" input
1. Set the number of colors you want to extract
1. The extracted colors will be available as dynamic color picker parameters (color_1, color_2, etc.)

### Parameters

#### Image Input

- **input_image**: The image to analyze (can be connected from other image nodes)
    - Supports common formats: JPG, PNG, GIF, BMP, TIFF, ICO, WEBP
    - Accepts ImageArtifact or ImageUrlArtifact
    - File browser integration for easy image selection

#### Color Settings

- **num_colors** (1-12, default: 3): Number of colors to extract
    - Slider interface for easy selection
    - Colors are ordered by prominence (most frequent first)
    - Each extracted color becomes a separate output parameter

- **algorithm** (default: kmeans): Color extraction algorithm to use
    - **kmeans**: Uses KMeans clustering for accurate color grouping
    - **median_cut**: Uses Modified Median Cut Quantization (MMCQ) for balanced color space division
    - Dropdown menu for easy selection

### Outputs

Dynamic color picker parameters are created for each extracted color:

- **color_1, color_2, etc.**: Hexadecimal color values (#RRGGBB)
    - Each parameter includes an interactive color picker UI
    - Colors are ordered by frequency (most dominant first)
    - Available in the Properties panel
    - Can be connected to other nodes for color-based workflows

## Example

A typical color extraction workflow:

1. Load or generate an image using LoadImage or GenerateImage
1. Connect that image to the ExtractKeyColors node's "input_image" parameter
1. Set num_colors to 5 to extract the top 5 dominant colors
1. The node will analyze the image and create 5 color parameters:
    - color_1: The most prominent color (highest frequency)
    - color_2: The second most prominent color
    - color_3: The third most prominent color
    - And so on...
1. View the extracted colors in the Properties panel
1. Connect the color outputs to other nodes for color-based processing

## Important Notes

- **Algorithm Choice**: Choose between KMeans (accurate clustering) and Median Cut (balanced color space)
- **Automatic Sorting**: Colors are automatically ordered by their frequency in the image
- **Color Diversity**: Both algorithms ensure extracted colors are distinct and representative
- **Dynamic Parameters**: The node creates only the number of color parameters you request
- **Real-time Processing**: Colors are extracted immediately when the image changes
- **Hex Format**: All colors are provided as hexadecimal values (#RRGGBB)
- **Compatibility**: Works with Pillow 11+ and NumPy 1.20+ without compatibility issues

## Common Issues

- **Too Few Colors**: Increase the num_colors setting to extract more colors
- **Similar Colors**: The KMeans algorithm ensures color diversity, but very similar images may produce similar colors
- **Processing Time**: Larger images may take longer to process
- **No Colors Extracted**: Check that your image source is properly connected and contains valid image data

## Technical Details

The node uses a sophisticated color extraction process:

1. **Image Conversion**: Converts input image to PIL Image format and ensures RGB color space
1. **Algorithm Selection**: Choose between two proven color extraction algorithms:
    - **KMeans**: Uses scikit-learn's KMeans clustering to identify dominant color clusters
        - Groups similar pixels into clusters based on perceptual similarity
        - Identifies representative colors for each cluster
        - Orders colors by cluster size (pixel count)
    - **Median Cut (MMCQ)**: Modified Median Cut Quantization algorithm
        - Iteratively divides color space into buckets
        - Always splits the bucket with the largest color range
        - Stops at exactly the requested number of colors
        - Orders colors by bucket size (pixel count)
1. **Frequency Analysis**: Each extracted color includes its frequency/prominence in the image
1. **Automatic Ordering**: Colors are automatically sorted by frequency (most prominent first)
1. **Color Diversity**: Both algorithms ensure extracted colors are distinct and representative
1. **Dynamic UI Creation**: Generates color picker parameters for each extracted color

### Algorithm Benefits

- **KMeans Algorithm**:
    - Accurate color clustering based on perceptual similarity
    - Excellent for images with distinct color regions
    - Handles gradients and transitions well
    
- **Median Cut Algorithm**:
    - Balanced color space representation
    - Classic quantization approach
    - Good for images with uniform color distribution
    - Faster than KMeans for large images

- **Shared Benefits**:
    - Native Python implementations using stable libraries (sklearn, numpy)
    - Compatible with Pillow 11+ and NumPy 1.20+
    - Efficient processing for images of various sizes
    - Built-in frequency data for each color

This provides a professional-grade solution for color extraction using modern, actively-maintained libraries, making it ideal for both creative and technical workflows.
