# ExtractKeyColors

## What is it?

The ExtractKeyColors node analyzes images and extracts the most prominent colors using Pylette's KMeans clustering algorithm. It automatically orders colors by their frequency in the image and creates dynamic color picker parameters for each extracted color, making it perfect for color palette generation, brand analysis, and design workflows.

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

- **KMeans Clustering**: Uses Pylette's optimized KMeans algorithm for perceptual color grouping
- **Automatic Sorting**: Colors are automatically ordered by their frequency in the image
- **Color Diversity**: Pylette ensures extracted colors are distinct and representative
- **Dynamic Parameters**: The node creates only the number of color parameters you request
- **Real-time Processing**: Colors are extracted immediately when the image changes
- **Hex Format**: All colors are provided as hexadecimal values (#RRGGBB)

## Common Issues

- **Too Few Colors**: Increase the num_colors setting to extract more colors
- **Similar Colors**: The KMeans algorithm ensures color diversity, but very similar images may produce similar colors
- **Processing Time**: Larger images may take longer to process
- **No Colors Extracted**: Check that your image source is properly connected and contains valid image data

## Technical Details

The node uses a sophisticated color extraction process:

1. **Image Conversion**: Converts input image to PIL Image format and ensures RGB color space
1. **KMeans Clustering**: Uses Pylette's KMeans algorithm to identify dominant color clusters
    - Groups similar pixels into clusters based on perceptual similarity
    - Identifies representative colors for each cluster
1. **Frequency Analysis**: Each extracted color includes its frequency/prominence in the image
1. **Automatic Ordering**: Colors are automatically sorted by frequency (most prominent first)
1. **Color Diversity**: Pylette ensures extracted colors are distinct and representative
1. **Dynamic UI Creation**: Generates color picker parameters for each extracted color

### Algorithm Benefits

- **Perceptual Grouping**: Colors are selected based on how humans perceive color similarity
- **Optimized Processing**: Efficient algorithm handles images of various sizes effectively
- **Automatic Diversity**: No need for manual filtering - colors are naturally distinct
- **Built-in Frequency Data**: Each color knows its prominence in the image

This provides a professional-grade solution for color extraction using modern, actively-maintained libraries, making it ideal for both creative and technical workflows.
