"""Image metadata injection drivers.

Provides pluggable drivers for injecting workflow metadata into different image formats.
Drivers are automatically registered on module import.
"""

from griptape_nodes.drivers.image_metadata.base_image_metadata_driver import BaseImageMetadataDriver
from griptape_nodes.drivers.image_metadata.exif_metadata_driver import ExifMetadataDriver
from griptape_nodes.drivers.image_metadata.image_metadata_driver_registry import ImageMetadataDriverRegistry
from griptape_nodes.drivers.image_metadata.png_metadata_driver import PngMetadataDriver

# Register core drivers on import
ImageMetadataDriverRegistry.register_driver(PngMetadataDriver())
ImageMetadataDriverRegistry.register_driver(ExifMetadataDriver())

__all__ = [
    "BaseImageMetadataDriver",
    "ExifMetadataDriver",
    "ImageMetadataDriverRegistry",
    "PngMetadataDriver",
]
