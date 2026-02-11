"""File read driver implementations for reading files from various sources."""

from griptape_nodes.file.drivers.data_uri_file_read_driver import DataUriFileReadDriver
from griptape_nodes.file.drivers.griptape_cloud_file_read_driver import GriptapeCloudFileReadDriver
from griptape_nodes.file.drivers.http_file_read_driver import HttpFileReadDriver
from griptape_nodes.file.drivers.local_file_read_driver import LocalFileReadDriver
from griptape_nodes.file.file_read_driver import FileReadDriverRegistry

# Register core drivers on import
# Order matters: most specific first, local last (fallback)
FileReadDriverRegistry.register(HttpFileReadDriver())
FileReadDriverRegistry.register(DataUriFileReadDriver())

# Register GriptapeCloudFileReadDriver if credentials available
cloud_driver = GriptapeCloudFileReadDriver.create_from_env()
if cloud_driver:
    FileReadDriverRegistry.register(cloud_driver)

# LocalFileReadDriver must be registered LAST (matches all absolute paths)
FileReadDriverRegistry.register(LocalFileReadDriver())

__all__ = [
    "DataUriFileReadDriver",
    "GriptapeCloudFileReadDriver",
    "HttpFileReadDriver",
    "LocalFileReadDriver",
]
