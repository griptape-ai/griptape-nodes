from enum import StrEnum, auto
from pathlib import Path
from typing import Any

from griptape.artifacts import ImageArtifact, ImageUrlArtifact

from griptape_nodes.exe_types.core_types import (
    Parameter,
    ParameterGroup,
    ParameterMode,
)
from griptape_nodes.exe_types.node_types import SuccessFailureNode
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes, logger
from griptape_nodes_library.utils.image_utils import dict_to_image_url_artifact, load_image_from_url_artifact

DEFAULT_FILENAME = "griptape_nodes.png"
PREVIEW_LENGTH = 50


class SaveImageStatus(StrEnum):
    """Status enum for save image operations."""

    SUCCESS = auto()
    WARNING = auto()
    FAILURE = auto()


def to_image_artifact(image: ImageArtifact | dict) -> ImageArtifact | ImageUrlArtifact:
    """Convert an image or a dictionary to an ImageArtifact."""
    if isinstance(image, dict):
        return dict_to_image_url_artifact(image)
    return image


class SaveImage(SuccessFailureNode):
    """Save an image to a file."""

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)

        # Add image input parameter
        self.add_parameter(
            Parameter(
                name="image",
                input_types=["ImageArtifact", "ImageUrlArtifact", "dict"],
                type="ImageUrlArtifact",
                allowed_modes={ParameterMode.INPUT},
                tooltip="The image to save to file",
            )
        )

        # Add output path parameter
        self.add_parameter(
            Parameter(
                name="output_path",
                input_types=["str"],
                type="str",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY, ParameterMode.OUTPUT},
                default_value=DEFAULT_FILENAME,
                tooltip="The output filename with extension (.png, .jpg, etc.)",
            )
        )

        # Save options parameters in a collapsible ParameterGroup
        with ParameterGroup(name="Save Options") as save_options_group:
            save_options_group.ui_options = {"collapsed": True}

            self.allow_creating_folders = Parameter(
                name="allow_creating_folders",
                tooltip="Allow creating parent directories if they don't exist",
                type="bool",
                default_value=True,
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )

            self.overwrite_existing = Parameter(
                name="overwrite_existing",
                tooltip="Allow overwriting existing files",
                type="bool",
                default_value=True,
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )

        self.add_node_element(save_options_group)

        # Add status parameters using the helper method
        self._create_status_parameters(
            result_details_tooltip="Details about the image save operation result",
            result_details_placeholder="Details on the save attempt will be presented here.",
        )

    def process(self) -> None:
        # Reset execution state and result details at the start of each run
        self._clear_execution_status()

        image = self.get_parameter_value("image")
        output_file = self.get_parameter_value("output_path") or DEFAULT_FILENAME

        # Set output values BEFORE processing
        self.parameter_output_values["output_path"] = output_file

        if not image:
            # Blank image is a warning, not a failure
            warning_details = "No image provided to save"
            logger.warning(warning_details)
            self._handle_execution_result(
                status=SaveImageStatus.WARNING,
                saved_path="",
                input_info="No image input",
                output_file=output_file,
                details=warning_details,
            )
            return

        # Capture input source details for forensics
        input_info = self._get_input_info(image)

        # Convert ImageUrlArtifact to ImageArtifact if needed
        processed_image = image
        if isinstance(image, ImageUrlArtifact):
            try:
                processed_image = load_image_from_url_artifact(image)
            except Exception as e:
                error_details = f"Failed to load image from URL: {e!s}"
                self._handle_error_with_graceful_exit(error_details, e, input_info, output_file)
                return

        # Convert to appropriate artifact type
        try:
            image_artifact = to_image_artifact(processed_image)
        except Exception as e:
            error_details = f"Failed to convert image to artifact: {e!s}"
            self._handle_error_with_graceful_exit(error_details, e, input_info, output_file)
            return

        # Get save options
        allow_creating_folders = self.get_parameter_value(self.allow_creating_folders.name)
        overwrite_existing = self.get_parameter_value(self.overwrite_existing.name)

        # Save image using appropriate method based on path type
        try:
            output_path = Path(output_file)
            if output_path.is_absolute():
                # Full path: save directly to filesystem
                saved_path = self._save_to_filesystem(
                    image_artifact=image_artifact,
                    output_path=output_path,
                    allow_creating_folders=allow_creating_folders,
                    overwrite_existing=overwrite_existing,
                )
            else:
                # Relative path: use static file manager
                saved_path = self._save_to_static_storage(
                    image_artifact=image_artifact, output_file=output_file, overwrite_existing=overwrite_existing
                )
        except Exception as e:
            error_details = f"Failed to save image: {e!s}"
            self._handle_error_with_graceful_exit(error_details, e, input_info, output_file)
            return

        # Success case with path method info
        path_method = "filesystem" if output_path.is_absolute() else "static storage"
        success_details = f"Image saved successfully via {path_method}"
        self._handle_execution_result(
            status=SaveImageStatus.SUCCESS,
            saved_path=saved_path,
            input_info=input_info,
            output_file=output_file,
            details=success_details,
        )
        logger.info(f"Saved image: {saved_path}")

    def _get_input_info(self, image: Any) -> str:
        """Get input information for forensics logging."""
        input_type = type(image).__name__
        if isinstance(image, dict):
            return f"Dictionary input with type: {image.get('type', 'unknown')}"
        if isinstance(image, ImageUrlArtifact):
            return f"ImageUrlArtifact with URL: {image.value}"
        return f"ImageArtifact of type: {input_type}"

    def _get_input_info_for_failure(self, image: Any) -> str:
        """Get detailed input information for failure forensics logging."""
        input_type = type(image).__name__
        if isinstance(image, dict):
            input_info = f"Dictionary input with type: {image.get('type', 'unknown')}"
            if "value" in image:
                value_str = str(image["value"])
                value_preview = value_str[:PREVIEW_LENGTH] + "..." if len(value_str) > PREVIEW_LENGTH else value_str
                input_info += f", value preview: {value_preview}"
            return input_info
        if isinstance(image, ImageUrlArtifact):
            return f"ImageUrlArtifact with URL: {image.value}"
        return f"ImageArtifact of type: {input_type}"

    def _handle_execution_result(  # noqa: PLR0913
        self,
        status: SaveImageStatus,
        saved_path: str,
        input_info: str,
        output_file: str,
        details: str,
        exception: Exception | None = None,
    ) -> None:
        """Handle execution result for all cases."""
        match status:
            case SaveImageStatus.FAILURE:
                # Get detailed input info for failures (including dictionary preview)
                detailed_input_info = self._get_input_info_for_failure(self.get_parameter_value("image"))

                failure_details = f"Image save failed\nInput: {detailed_input_info}\nError: {details}"

                if exception:
                    failure_details += f"\nException type: {type(exception).__name__}"
                    if exception.__cause__:
                        failure_details += f"\nCause: {exception.__cause__}"

                self._set_status_results(was_successful=False, result_details=f"{status}: {failure_details}")
                logger.error(f"Error saving image: {details}")

            case SaveImageStatus.WARNING:
                result_details = (
                    f"No image to save (warning)\n"
                    f"Input: {input_info}\n"
                    f"Requested filename: {output_file}\n"
                    f"Result: No file created"
                )

                self._set_status_results(was_successful=True, result_details=f"{status}: {result_details}")

            case SaveImageStatus.SUCCESS:
                result_details = (
                    f"Image saved successfully\n"
                    f"Input: {input_info}\n"
                    f"Requested filename: {output_file}\n"
                    f"Saved to: {saved_path}"
                )

                self._set_status_results(was_successful=True, result_details=f"{status}: {result_details}")

    def _save_to_filesystem(
        self, image_artifact: Any, output_path: Path, *, allow_creating_folders: bool, overwrite_existing: bool
    ) -> str:
        """Save image directly to filesystem at the specified absolute path."""
        # Check if file exists and overwrite is disabled
        if output_path.exists() and not overwrite_existing:
            error_details = f"File already exists and overwrite_existing is disabled: {output_path}"
            raise RuntimeError(error_details)

        # Handle parent directory creation
        if allow_creating_folders:
            try:
                output_path.parent.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                error_details = f"Failed to create directory structure for path: {e!s}"
                raise RuntimeError(error_details) from e
        elif not output_path.parent.exists():
            error_details = (
                f"Parent directory does not exist and allow_creating_folders is disabled: {output_path.parent}"
            )
            raise RuntimeError(error_details)

        # Convert image to bytes
        try:
            image_bytes = image_artifact.to_bytes()
        except Exception as e:
            error_details = f"Failed to convert image artifact to bytes: {e!s}"
            raise RuntimeError(error_details) from e

        # Write image bytes directly to file
        try:
            output_path.write_bytes(image_bytes)
        except Exception as e:
            error_details = f"Failed to write image file to filesystem: {e!s}"
            raise RuntimeError(error_details) from e

        return str(output_path)

    def _save_to_static_storage(self, image_artifact: Any, output_file: str, *, overwrite_existing: bool) -> str:
        """Save image using the static file manager."""
        # Check if file exists in static storage and overwrite is disabled
        if not overwrite_existing:
            from griptape_nodes.retained_mode.events.static_file_events import (
                CreateStaticFileDownloadUrlRequest,
                CreateStaticFileDownloadUrlResultFailure,
            )

            static_files_manager = GriptapeNodes.StaticFilesManager()
            request = CreateStaticFileDownloadUrlRequest(file_name=output_file)
            result = static_files_manager.on_handle_create_static_file_download_url_request(request)

            if not isinstance(result, CreateStaticFileDownloadUrlResultFailure):
                error_details = (
                    f"File already exists in static storage and overwrite_existing is disabled: {output_file}"
                )
                raise RuntimeError(error_details)

        # Convert image to bytes
        try:
            image_bytes = image_artifact.to_bytes()
        except Exception as e:
            error_details = f"Failed to convert image artifact to bytes: {e!s}"
            raise RuntimeError(error_details) from e

        # Save to static storage
        try:
            return GriptapeNodes.StaticFilesManager().save_static_file(image_bytes, output_file)
        except Exception as e:
            error_details = f"Failed to save image to static storage: {e!s}"
            raise RuntimeError(error_details) from e

    def _handle_error_with_graceful_exit(
        self, error_details: str, exception: Exception, input_info: str, output_file: str
    ) -> None:
        """Handle error with graceful exit if failure output is connected."""
        self._handle_execution_result(
            status=SaveImageStatus.FAILURE,
            saved_path="",
            input_info=input_info,
            output_file=output_file,
            details=error_details,
            exception=exception,
        )
        # Use the helper to handle exception based on connection status
        self._handle_failure_exception(RuntimeError(error_details))
