# DisplayImageGrid

## What is it?

The DisplayImageGrid node allows you to display multiple images in a grid or masonry layout with customizable styling options, preset output sizes, and flexible alignment controls. It's perfect for creating image galleries, showcasing multiple results, or presenting image collections in an organized, visually appealing format with professional output quality.

## When would I use it?

Use this node when you want to:

- Create image galleries or portfolios
- Display multiple image generation results
- Showcase different versions of processed images
- Create image collections or albums
- Present multiple image options for review
- Build image-based presentations
- Organize images in a grid layout
- Export grids at standard video resolutions (4K, 1440p, 1080p, 720p)

## How to use it

### Basic Setup

1. Add the DisplayImageGrid node to your workflow
1. Connect multiple image sources to the "images" input
1. Choose your layout style and customize the appearance
1. Select output size mode (custom or preset)
1. The grid will be displayed with all your images

### Parameters

#### Image Input

- **images**: List of images to display in the grid

#### Layout Settings

- **layout_style**: The arrangement style for the images

    - **grid**: Regular grid layout with equal-sized cells
    - **masonry**: Pinterest-style layout with varying heights

- **grid_justification** (grid layout only): Horizontal alignment of images in incomplete rows

    - **left**: Align images to the left (default)
    - **center**: Center images horizontally
    - **right**: Align images to the right

- **columns** (1-10, default: 4): Number of columns in the grid

- **spacing** (0-100, default: 10): Space between images in pixels

#### Styling Options

- **crop_to_fit** (boolean, default: true): Crop images to fit perfectly within the grid cells for clean borders

- **transparent_bg** (boolean, default: false): Use transparent background instead of solid color

- **background_color** (hex color, default: #000000): Background color for the grid (visible by default)

- **border_radius** (0-500, default: 8): Corner radius for rounded corners (0 for square)

#### Output Settings

- **output_image_size**: Choose between custom width or preset sizes

    - **custom**: Use a custom width value
    - **preset**: Use standard video resolutions

- **output_image_width** (default: 1200): Maximum width in pixels (shown when custom is selected)

- **output_preset**: Standard video resolutions (shown when preset is selected)

    - **4K (3840x2160)**: Ultra HD resolution
    - **1440p (2560x1440)**: Quad HD resolution
    - **1080p (1920x1080)**: Full HD resolution
    - **720p (1280x720)**: HD resolution

- **output_format**: Output file format

    - **png**: Best quality, supports transparency
    - **jpeg**: Smaller file size, no transparency
    - **webp**: Modern format with good compression

### Outputs

- **output**: The formatted image grid as an ImageUrlArtifact

## Example

A typical image grid workflow:

1. Generate multiple images using GenerateImage nodes
1. Connect all images to the DisplayImageGrid node's "images" parameter
1. Set the layout settings:
    - Select "grid" layout_style for uniform tiles
    - Set grid_justification to "center" to center incomplete rows
    - Set columns to 4 for a 4-column grid
    - Set spacing to 10 for comfortable spacing between images
1. Customize the appearance:
    - Set background_color to "#000000" (black) for a dark background
    - Set border_radius to 8 for rounded corners
    - Enable crop_to_fit for clean borders
1. Choose output size:
    - Select "preset" for output_image_size
    - Choose "1080p (1920x1080)" for Full HD output
1. The grid will display all your images in an organized, attractive layout at exactly 1920×1080 pixels

## Important Notes

- **Flexible Layout**: Choose between grid and masonry layouts
- **Preset Sizes**: Export at standard video resolutions (4K, 1440p, 1080p, 720p)
- **Smart Scaling**: When using presets, the grid scales proportionally to fit without distortion
- **Justification Control**: Align incomplete rows left, center, or right (grid layout only)
- **Background Control**: Choose between solid colors or transparent backgrounds
- **Customizable Styling**: Full control over colors, spacing, and appearance
- **Multiple Images**: Can handle any number of input images
- **No Cropping**: When using presets, images are scaled to fit (not cropped), with padding as needed

## Common Issues

- **No Images Showing**: Make sure you've connected images to the "images" parameter
- **Layout Issues**: Adjust columns and spacing for better appearance
- **Images Too Small**: Increase the overall grid size or reduce the number of columns
- **Preset Output Different Than Expected**: Preset mode scales the grid to fit within the exact dimensions while maintaining aspect ratio

## Technical Details

The node creates a responsive grid layout that:

- Automatically arranges images in the specified layout style
- Maintains aspect ratios while fitting images to the grid
- Provides consistent spacing and styling
- Supports both regular grid and masonry layouts
- When using presets, creates a canvas at exact dimensions and scales the grid proportionally
- Applies justification for horizontal positioning in grid layout
- Centers the grid vertically with background padding when needed

This is perfect for creating professional-looking image galleries and collections at standard output resolutions.
