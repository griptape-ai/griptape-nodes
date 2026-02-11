"""Loader driver implementations for reading files from various sources."""

from griptape_nodes.file.drivers.data_uri_loader_driver import DataUriLoaderDriver
from griptape_nodes.file.drivers.griptape_cloud_loader_driver import GriptapeCloudLoaderDriver
from griptape_nodes.file.drivers.http_loader_driver import HttpLoaderDriver
from griptape_nodes.file.drivers.local_loader_driver import LocalLoaderDriver
from griptape_nodes.file.loader_driver import LoaderDriverRegistry

# Register core drivers on import
# Order matters: most specific first, local last (fallback)
LoaderDriverRegistry.register(HttpLoaderDriver())
LoaderDriverRegistry.register(DataUriLoaderDriver())

# Register GriptapeCloudLoaderDriver if credentials available
cloud_driver = GriptapeCloudLoaderDriver.create_from_env()
if cloud_driver:
    LoaderDriverRegistry.register(cloud_driver)

# LocalLoaderDriver must be registered LAST (matches all absolute paths)
LoaderDriverRegistry.register(LocalLoaderDriver())

__all__ = [
    "DataUriLoaderDriver",
    "GriptapeCloudLoaderDriver",
    "HttpLoaderDriver",
    "LocalLoaderDriver",
]
