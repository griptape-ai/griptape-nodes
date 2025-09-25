# SaveImage

## What is it?

The SaveImage node allows you to save images to your local file system. It's a simple but essential node for preserving the results of your image processing workflows, allowing you to export images in various formats and quality settings.

## When would I use it?

Use this node when you want to:

- Save processed images to your computer
- Export images in specific formats (PNG, JPEG, etc.)
- Control image quality and compression settings
- Preserve the results of your image processing workflows
- Create backups of important images
- Export images for use in other applications

## How to use it

### Basic Setup

1. Add the SaveImage node to your workflow
1. Connect an image source to the "input_image" input
1. Set the output file path and format
1. The image will be saved to the specified location

### Parameters

#### Image Input

- **input_image**: The image to save (can be connected from any image processing node)

#### Output Settings

- **output_path**: The file path where the image will be saved

    - Can be a relative path (e.g., "output/image.png")
    - Can be an absolute path (e.g., "/Users/username/Desktop/image.png")
    - File extension determines the format

- **image_format**: The format to save the image in

    - **PNG**: Lossless format, supports transparency
    - **JPEG**: Compressed format, smaller file sizes
    - **BMP**: Uncompressed bitmap format
    - **TIFF**: High-quality format for professional use

#### Quality Settings (JPEG only)

- **quality** (1-100, default: 95): JPEG compression quality
    - Higher values = better quality, larger files
    - Lower values = lower quality, smaller files

### Outputs

- **saved_path**: The path where the image was saved
- **file_size**: The size of the saved file in bytes

## Example

A typical image saving workflow:

1. Process an image using AdjustImageEQ or another processing node
1. Connect the processed image to the SaveImage node's "input_image" parameter
1. Set the output settings:
    - Set output_path to "processed_image.png"
    - Select "PNG" image_format for lossless quality
1. The image will be saved to your specified location
1. The saved_path output will show where the file was saved

## Important Notes

- **File Paths**: Make sure the output directory exists or the node will create it
- **Format Support**: Different formats support different features (transparency, compression, etc.)
- **Quality Control**: JPEG quality setting only affects JPEG format
- **Overwrite Protection**: The node will overwrite existing files with the same name

## Common Issues

- **File Not Saved**: Check that the output_path is valid and you have write permissions
- **Wrong Format**: Make sure the file extension matches the image_format setting
- **Poor Quality**: For JPEG, increase the quality setting

## Technical Details

The node uses PIL's image saving capabilities:

- **PNG**: Lossless compression with transparency support
- **JPEG**: Lossy compression with quality control
- **BMP**: Uncompressed bitmap format
- **TIFF**: High-quality format with various compression options

This provides reliable image saving functionality for any workflow that needs to preserve results.
