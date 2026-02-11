"""File location loading drivers.

Provides pluggable drivers for loading and saving files from different location types.
Drivers are automatically registered on module import.

Built-in drivers:
- DataUriDriver: Handles "data:image/png;base64,..." URIs (read-only)
- HttpDriver: Handles "http://" and "https://" URLs (read-only)
- GriptapeCloudDriver: Handles Griptape Cloud asset URLs (bidirectional, if credentials available)
- FilePathDriver: Handles filesystem paths (bidirectional, fallback)

Custom drivers can be registered via LocationDriverRegistry.register_driver().
"""

from griptape_nodes.drivers.location.base_location_driver import BaseLocationDriver
from griptape_nodes.drivers.location.data_uri_driver import DataUriDriver
from griptape_nodes.drivers.location.file_path_driver import FilePathDriver
from griptape_nodes.drivers.location.griptape_cloud_driver import GriptapeCloudDriver
from griptape_nodes.drivers.location.http_driver import HttpDriver
from griptape_nodes.drivers.location.location_driver_registry import LocationDriverRegistry

# Register built-in drivers (order matters - most specific first, fallback last)
LocationDriverRegistry.register_driver(DataUriDriver())
LocationDriverRegistry.register_driver(HttpDriver())

# GTC driver - conditionally register if credentials available
GriptapeCloudDriver.register_if_available()

# File path driver MUST BE LAST (fallback)
LocationDriverRegistry.register_driver(FilePathDriver())

__all__ = [
    "BaseLocationDriver",
    "DataUriDriver",
    "FilePathDriver",
    "GriptapeCloudDriver",
    "HttpDriver",
    "LocationDriverRegistry",
]
