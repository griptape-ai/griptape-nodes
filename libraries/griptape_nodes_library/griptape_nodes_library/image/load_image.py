from pathlib import Path
from typing import Any

import httpx

from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.exe_types.node_types import DataNode
from griptape_nodes.retained_mode.events.static_file_events import (
    CreateStaticFileDownloadUrlRequest,
    CreateStaticFileDownloadUrlResultFailure,
    CreateStaticFileDownloadUrlResultSuccess,
    CreateStaticFileUploadUrlRequest,
    CreateStaticFileUploadUrlResultFailure,
    CreateStaticFileUploadUrlResultSuccess,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes_library.utils.image_utils import dict_to_image_url_artifact


class LoadImage(DataNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        # Tracks which parameter is currently driving updates to prevent infinite loops
        # when file_path changes trigger image updates and vice versa
        self._updating_from_parameter = None

        # Need to define the category
        self.category = "Image"
        self.description = "Load an image"
        self.image_parameter = Parameter(
            name="image",
            input_types=["ImageArtifact", "ImageUrlArtifact"],
            type="ImageArtifact",
            output_type="ImageUrlArtifact",
            default_value=None,
            ui_options={"clickable_file_browser": True, "expander": True, "edit_mask": True},
            tooltip="The image that has been generated.",
        )
        self.add_parameter(self.image_parameter)

        self.file_path_parameter = Parameter(
            name="file_path",
            input_types=["str"],
            type="str",
            default_value="",
            tooltip="Path to an image file to load",
        )
        self.add_parameter(self.file_path_parameter)

    def _to_image_artifact(self, image: Any) -> Any:
        if isinstance(image, dict):
            # Preserve any existing metadata
            metadata = image.get("meta", {})
            artifact = dict_to_image_url_artifact(image)
            if metadata:
                artifact.meta = metadata
            return artifact
        return image

    def _is_valid_image_file(self, file_path: str) -> bool:
        """Check if file has a valid image extension and exists."""
        if not file_path.strip():
            return False

        path = Path(file_path)
        if not path.exists():
            error_msg = f"Image file not found: {file_path}"
            raise FileNotFoundError(error_msg)

        if not path.is_file():
            error_msg = f"Path is not a file: {file_path}"
            raise ValueError(error_msg)

        valid_extensions = {".png", ".jpg", ".jpeg", ".webp"}
        if path.suffix.lower() not in valid_extensions:
            supported = ", ".join(valid_extensions)
            error_msg = f"Unsupported image format: {path.suffix}. Supported formats: {supported}"
            raise ValueError(error_msg)

        return True

    def _upload_file_to_static_storage(self, file_path: str) -> str:
        """Upload file to static storage and return download URL."""
        path = Path(file_path)
        file_name = path.name

        # Create upload URL
        upload_request = CreateStaticFileUploadUrlRequest(file_name=file_name)
        upload_result = GriptapeNodes.handle_request(upload_request)

        if isinstance(upload_result, CreateStaticFileUploadUrlResultFailure):
            error_msg = f"Failed to create upload URL: {upload_result.error}"
            raise TypeError(error_msg)

        if not isinstance(upload_result, CreateStaticFileUploadUrlResultSuccess):
            error_msg = f"Unexpected upload URL result type: {type(upload_result)}"
            raise TypeError(error_msg)

        # Read and upload file
        try:
            file_data = path.read_bytes()
        except Exception as e:
            error_msg = f"Failed to read file {file_path}: {e}"
            raise ValueError(error_msg) from e

        try:
            response = httpx.request(
                upload_result.method,
                upload_result.url,
                content=file_data,
                headers=upload_result.headers,
            )
            response.raise_for_status()
        except Exception as e:
            error_msg = f"Failed to upload file: {e}"
            raise ValueError(error_msg) from e

        # Get download URL
        download_request = CreateStaticFileDownloadUrlRequest(file_name=file_name)
        download_result = GriptapeNodes.handle_request(download_request)

        if isinstance(download_result, CreateStaticFileDownloadUrlResultFailure):
            error_msg = f"Failed to create download URL: {download_result.error}"
            raise TypeError(error_msg)

        if not isinstance(download_result, CreateStaticFileDownloadUrlResultSuccess):
            error_msg = f"Unexpected download URL result type: {type(download_result)}"
            raise TypeError(error_msg)

        return download_result.url

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        # Skip if we're already updating from this parameter to prevent infinite loops
        if self._updating_from_parameter == parameter:
            return super().after_value_set(parameter, value)

        if parameter.name == self.image_parameter.name:
            image_artifact = self._to_image_artifact(value)
            self.parameter_output_values[self.image_parameter.name] = image_artifact
        elif parameter.name == self.file_path_parameter.name:
            file_path = str(value).strip() if value else ""
            # Strip surrounding quotes only if they match (from "Copy as Pathname")
            if len(file_path) >= 2 and (  # noqa: PLR2004
                (file_path.startswith("'") and file_path.endswith("'"))
                or (file_path.startswith('"') and file_path.endswith('"'))
            ):
                file_path = file_path[1:-1]

            # Indicate that we're the controlling parameter so we don't trigger an infinite cascade of set value changes.
            self._updating_from_parameter = parameter
            try:
                if file_path and self._is_valid_image_file(file_path):
                    download_url = self._upload_file_to_static_storage(file_path)
                    # Test that artifact creation works before updating the image parameter
                    image_artifact = self._to_image_artifact({"value": download_url, "type": "ImageUrlArtifact"})
                    # Only update image parameter if artifact creation succeeded
                    self.set_parameter_value(
                        self.image_parameter.name, {"value": download_url, "type": "ImageUrlArtifact"}
                    )
                else:
                    # Empty file path - reset the image parameter to None
                    self.set_parameter_value(self.image_parameter.name, None)
            except Exception as e:
                # Re-raise the exception to show error to user
                error_msg = f"Failed to process image file: {e}"
                raise ValueError(error_msg) from e
            finally:
                # Clear the update lock to allow future parameter updates
                self._updating_from_parameter = None
        return super().after_value_set(parameter, value)

    def process(self) -> None:
        image = self.get_parameter_value("image")
        image_artifact = self._to_image_artifact(image)
        self.parameter_output_values["image"] = image_artifact
