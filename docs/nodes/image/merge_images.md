# MergeImages

## What is it?

The MergeImages node allows you to combine multiple images into a single composition using different layout options. It's perfect for creating collages, image grids, or combining related images into one cohesive composition with flexible arrangement options.

## When would I use it?

Use this node when you want to:

- Create image collages or grids
- Combine multiple related images
- Create image mosaics or patterns
- Build image galleries or portfolios
- Combine images for comparison
- Create social media image layouts
- Build image-based presentations

## How to use it

### Basic Setup

1. Add the MergeImages node to your workflow
1. Connect multiple image sources to the "input_images" input
1. Choose your layout style and arrangement
1. The merged image will be available at the "output" parameter

### Parameters

#### Image Input

- **input_images**: List of images to merge (can be connected from multiple image sources)

#### Layout Settings

- **layout_style**: The arrangement style for the images

    - **grid**: Regular grid layout with equal-sized cells
    - **horizontal**: Arrange images in a horizontal row
    - **vertical**: Arrange images in a vertical column
    - **masonry**: Pinterest-style layout with varying heights

- **columns** (1-10, default: 3): Number of columns in grid layout

- **spacing** (0-50, default: 10): Space between images in pixels

#### Styling Options

- **background_color** (hex color, default: #ffffff): Background color for the merged image
- **border_radius** (0-20, default: 0): Corner radius for image borders
- **padding** (0-100, default: 20): Padding around the entire composition

### Outputs

- **output**: The merged image with all input images combined

## Example

A typical image merging workflow:

1. Load multiple images using LoadImage nodes
1. Connect all images to the MergeImages node's "input_images" parameter
1. Set the layout settings:
    - Select "grid" layout_style for a regular grid
    - Set columns to 2 for a 2-column layout
    - Set spacing to 15 for comfortable spacing between images
1. Customize the appearance:
    - Set background_color to "#f0f0f0" for a light gray background
    - Set border_radius to 5 for slightly rounded corners
    - Set padding to 30 for space around the entire composition
1. Connect the "output" to DisplayImage to view the result

## Important Notes

- **Flexible Layout**: Choose from multiple layout styles
- **Automatic Arrangement**: Images are automatically arranged based on your settings
- **Customizable Styling**: Full control over colors, spacing, and appearance
- **Multiple Images**: Can handle any number of input images

## Common Issues

- **No Images Showing**: Make sure you've connected images to the "input_images" parameter
- **Layout Issues**: Adjust columns and spacing for better appearance
- **Images Too Small**: Increase the overall composition size or reduce the number of columns

## Technical Details

The node creates a composite image that:

- Automatically arranges input images in the specified layout
- Maintains aspect ratios while fitting images to the layout
- Provides consistent spacing and styling
- Supports multiple layout styles for different use cases

This provides a powerful way to create complex image compositions from multiple sources.
