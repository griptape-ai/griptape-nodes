# Base Image Processor

The `BaseImageProcessor` class provides a foundation for creating image editing nodes that use PIL (Python Imaging Library) for image processing. This base class handles common functionality like parameter setup, validation, logging, and output management.

## Key Features

- **Common Parameters**: All image processors automatically get image input, output format, quality, and output parameters
- **PIL Integration**: Built-in support for PIL image loading, processing, and saving
- **Format Support**: Automatic format detection and conversion with quality control
- **Logging**: Built-in logging system for processing events and errors
- **Validation**: Common validation patterns for image inputs and custom parameters
- **File Management**: Automatic temporary file handling and cleanup
- **Utility Integration**: Leverages existing `image_utils.py` functions to avoid code duplication

## Creating a New Image Processor

To create a new image processing node, inherit from `BaseImageProcessor` and implement the required abstract methods:

### Required Methods

1. **`_setup_custom_parameters()`**: Define your node's specific parameters
1. **`_get_processing_description()`**: Return a description of what your processor does
1. **`_process_image(pil_image, **kwargs)`**: Implement your image processing logic

### Optional Methods

- **`_validate_custom_parameters()`**: Add custom validation for your parameters
- **`_get_custom_parameters()`**: Return a dict of your custom parameters
- **`_get_output_suffix()`**: Customize the output filename suffix

## Example Implementation

```python
from typing import Any
from PIL import Image
from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes_library.image.base_image_processor import BaseImageProcessor

class MyImageProcessor(BaseImageProcessor):
    def _setup_custom_parameters(self) -> None:
        # Add your custom parameters here
        self.add_parameter(
            Parameter(
                name="my_param",
                type="float",
                default_value=1.0,
                tooltip="My custom parameter"
            )
        )

    def _get_processing_description(self) -> str:
        return "my custom image processing"

    def _process_image(self, pil_image: Image.Image, **kwargs) -> None:
        # Implement your image processing logic here
        my_param = kwargs.get("my_param", 1.0)
        
        # Process the image...
        processed_image = pil_image  # Your processing here
        
        return processed_image

    def _get_custom_parameters(self) -> dict[str, Any]:
        return {
            "my_param": self.get_parameter_value("my_param")
        }
```

## Common Parameters

All image processors automatically include these parameters:

- **`image`**: Input image (ImageUrlArtifact or ImageArtifact)
- **`output_format`**: Output format (auto, PNG, JPEG, WEBP, etc.)
- **`quality`**: Quality setting for lossy formats (1-100)
- **`output`**: Output image (ImageUrlArtifact)
- **`logs`**: Processing logs (hidden by default)

## Resample Filter Options

The base class provides common resample filter options for resizing operations:

- `nearest`: Fastest, lowest quality
- `box`: Good for downscaling
- `bilinear`: Good balance
- `hamming`: Good for downscaling
- `bicubic`: High quality, slower
- `lanczos`: Highest quality, slowest

## Image Format Options

Supported output formats:

- `auto`: Preserve input format
- `PNG`: Lossless, good for graphics
- `JPEG`: Lossy, good for photos
- `WEBP`: Modern, good compression

**Note**: GIF, BMP, and TIFF formats are not included in the base processor as they are specialized formats that don't align well with most image editing operations. Dedicated nodes for GIF/movie creation and specialized format handling can be created separately.

## Best Practices

1. **Use the base class constants** for common values and limits
1. **Implement proper validation** in `_validate_custom_parameters()`
1. **Handle edge cases** in your `_process_image()` method
1. **Use meaningful suffixes** in `_get_output_suffix()` for file naming
1. **Leverage the built-in logging** for debugging and user feedback

## Example Nodes

- **`RescaleImage`**: Demonstrates resizing with different modes and filters
- **`AdjustImageEQ`**: Shows basic image enhancement using PIL's ImageEnhance

These examples show how to create powerful image processing nodes with minimal code while leveraging all the base class functionality.
