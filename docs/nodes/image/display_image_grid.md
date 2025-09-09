# DisplayImageGrid

## What is it?

The DisplayImageGrid node allows you to display multiple images in a grid or masonry layout with customizable styling options. It's perfect for creating image galleries, showcasing multiple results, or presenting image collections in an organized, visually appealing format.

## When would I use it?

Use this node when you want to:

- Create image galleries or portfolios
- Display multiple image generation results
- Showcase different versions of processed images
- Create image collections or albums
- Present multiple image options for review
- Build image-based presentations
- Organize images in a grid layout

## How to use it

### Basic Setup

1. Add the DisplayImageGrid node to your workflow
1. Connect multiple image sources to the "input_images" input
1. Choose your layout style and customize the appearance
1. The grid will be displayed with all your images

### Parameters

#### Image Input

- **input_images**: List of images to display in the grid

#### Layout Settings

- **layout_style**: The arrangement style for the images

    - **grid**: Regular grid layout with equal-sized cells
    - **masonry**: Pinterest-style layout with varying heights

- **columns** (1-10, default: 3): Number of columns in the grid

- **spacing** (0-50, default: 10): Space between images in pixels

#### Styling Options

- **background_color** (hex color, default: #ffffff): Background color for the grid
- **border_radius** (0-20, default: 5): Corner radius for image borders
- **show_captions** (boolean, default: false): Show captions below images
- **caption_font_size** (8-24, default: 12): Size of caption text

### Outputs

- **grid_display**: The formatted image grid

## Example

A typical image grid workflow:

1. Generate multiple images using GenerateImage nodes
1. Connect all images to the DisplayImageGrid node's "input_images" parameter
1. Set the layout settings:
    - Select "masonry" layout_style for a Pinterest-style layout
    - Set columns to 4 for a 4-column grid
    - Set spacing to 15 for comfortable spacing between images
1. Customize the appearance:
    - Set background_color to "#f8f9fa" for a light gray background
    - Set border_radius to 8 for rounded corners
    - Enable show_captions to display image information
1. The grid will display all your images in an organized, attractive layout

## Important Notes

- **Flexible Layout**: Choose between grid and masonry layouts
- **Responsive Design**: The grid adapts to different screen sizes
- **Customizable Styling**: Full control over colors, spacing, and appearance
- **Multiple Images**: Can handle any number of input images

## Common Issues

- **No Images Showing**: Make sure you've connected images to the "input_images" parameter
- **Layout Issues**: Adjust columns and spacing for better appearance
- **Images Too Small**: Increase the overall grid size or reduce the number of columns

## Technical Details

The node creates a responsive grid layout that:

- Automatically arranges images in the specified layout style
- Maintains aspect ratios while fitting images to the grid
- Provides consistent spacing and styling
- Supports both regular grid and masonry layouts

This is perfect for creating professional-looking image galleries and collections.
