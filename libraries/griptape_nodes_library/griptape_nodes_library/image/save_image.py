from enum import StrEnum, auto
from pathlib import Path
from typing import Any

from griptape.artifacts import ImageArtifact, ImageUrlArtifact

from griptape_nodes.exe_types.core_types import (
    ControlParameterOutput,
    Parameter,
    ParameterGroup,
    ParameterMode,
)
from griptape_nodes.exe_types.node_types import ControlNode
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


class SaveImage(ControlNode):
    """Save an image to a file."""

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata, output_control_name="Succeeded")

        # Add Failed control output
        self.failure_output = ControlParameterOutput(
            name="failure",
            tooltip="Control path when the image save fails",
            display_name="Failed",
        )
        self.add_parameter(self.failure_output)

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

        # Track execution state for control flow routing
        self._execution_succeeded: bool | None = None

        # Advanced parameters in a collapsible ParameterGroup
        with ParameterGroup(name="Status") as group:
            group.ui_options = {"collapsed": True}

            # Boolean parameter to indicate success/failure
            self.was_successful = Parameter(
                name="was_successful",
                tooltip="Indicates whether it completed without errors.",
                type="bool",
                default_value=False,
                settable=False,
                allowed_modes={ParameterMode.OUTPUT},
            )

            # Result details parameter with multiline option
            self.result_details = Parameter(
                name="result_details",
                tooltip="Details about the image save operation result",
                type="str",
                default_value="The output of the operation will be presented here.",
                allowed_modes={ParameterMode.OUTPUT},
                settable=False,
                ui_options={"multiline": True},
            )

        self.add_node_element(group)

    def process(self) -> None:  # noqa: C901, PLR0912, PLR0915
        # Reset execution state and result details at the start of each run
        self._execution_succeeded = None
        self._assign_result_details("")
        self.parameter_output_values[self.was_successful.name] = False

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
            else:
                # Convert to appropriate artifact type
                try:
                    image_artifact = to_image_artifact(processed_image)
                except Exception as e:
                    error_details = f"Failed to convert image to artifact: {e!s}"
                    self._handle_error_with_graceful_exit(error_details, e, input_info, output_file)
                else:
                    # Save image using appropriate method based on path type
                    try:
                        output_path = Path(output_file)
                        if output_path.is_absolute():
                            # Full path: save directly to filesystem
                            saved_path = self._save_to_filesystem(image_artifact, output_path)
                        else:
                            # Relative path: use static file manager
                            saved_path = self._save_to_static_storage(image_artifact, output_file)
                    except Exception as e:
                        error_details = f"Failed to save image: {e!s}"
                        self._handle_error_with_graceful_exit(error_details, e, input_info, output_file)
                    else:
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
        else:
            # Convert to appropriate artifact type
            try:
                image_artifact = to_image_artifact(processed_image)
            except Exception as e:
                error_details = f"Failed to convert image to artifact: {e!s}"
                self._handle_error_with_graceful_exit(error_details, e, input_info, output_file)
            else:
                # Save image using appropriate method based on path type
                try:
                    output_path = Path(output_file)
                    if output_path.is_absolute():
                        # Full path: save directly to filesystem
                        saved_path = self._save_to_filesystem(image_artifact, output_path)
                    else:
                        # Relative path: use static file manager
                        saved_path = self._save_to_static_storage(image_artifact, output_file)
                except Exception as e:
                    error_details = f"Failed to save image: {e!s}"
                    self._handle_error_with_graceful_exit(error_details, e, input_info, output_file)
                else:
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

    def get_next_control_output(self) -> Parameter | None:
        """Determine which control output to follow based on execution result."""
        if self._execution_succeeded is None:
            # Execution hasn't completed yet
            self.stop_flow = True
            return None

        if self._execution_succeeded:
            # Return the existing control output (now renamed to "Succeeded")
            return self.control_parameter_out
        return self.failure_output

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
                self._execution_succeeded = False
                self.parameter_output_values[self.was_successful.name] = False

                # Get detailed input info for failures (including dictionary preview)
                detailed_input_info = self._get_input_info_for_failure(self.get_parameter_value("image"))

                failure_details = f"Image save failed\nInput: {detailed_input_info}\nError: {details}"

                if exception:
                    failure_details += f"\nException type: {type(exception).__name__}"
                    if exception.__cause__:
                        failure_details += f"\nCause: {exception.__cause__}"

                self._assign_result_details(f"{status}: {failure_details}")
                logger.error(f"Error saving image: {details}")

            case SaveImageStatus.WARNING:
                self._execution_succeeded = True
                self.parameter_output_values[self.was_successful.name] = True

                result_details = (
                    f"No image to save (warning)\n"
                    f"Input: {input_info}\n"
                    f"Requested filename: {output_file}\n"
                    f"Result: No file created"
                )

                self._assign_result_details(f"{status}: {result_details}")

            case SaveImageStatus.SUCCESS:
                self._execution_succeeded = True
                self.parameter_output_values[self.was_successful.name] = True

                result_details = (
                    f"Image saved successfully\n"
                    f"Input: {input_info}\n"
                    f"Requested filename: {output_file}\n"
                    f"Saved to: {saved_path}"
                )

                self._assign_result_details(f"{status}: {result_details}")

    def _save_to_filesystem(self, image_artifact: Any, output_path: Path) -> str:
        """Save image directly to filesystem at the specified absolute path."""
        # Ensure parent directory exists
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            error_details = f"Failed to create directory structure for path: {e!s}"
            raise ValueError(error_details) from e

        # Convert image to bytes
        try:
            image_bytes = image_artifact.to_bytes()
        except Exception as e:
            error_details = f"Failed to convert image artifact to bytes: {e!s}"
            raise ValueError(error_details) from e

        # Write image bytes directly to file
        try:
            output_path.write_bytes(image_bytes)
        except Exception as e:
            error_details = f"Failed to write image file to filesystem: {e!s}"
            raise ValueError(error_details) from e

        return str(output_path)

    def _save_to_static_storage(self, image_artifact: Any, output_file: str) -> str:
        """Save image using the static file manager (existing behavior)."""
        # Convert image to bytes
        try:
            image_bytes = image_artifact.to_bytes()
        except Exception as e:
            error_details = f"Failed to convert image artifact to bytes: {e!s}"
            raise ValueError(error_details) from e

        # Save to static storage
        try:
            return GriptapeNodes.StaticFilesManager().save_static_file(image_bytes, output_file)
        except Exception as e:
            error_details = f"Failed to save image to static storage: {e!s}"
            raise ValueError(error_details) from e

    def _assign_result_details(self, message: str) -> None:
        """Helper to assign result_details using publish_update_to_parameter."""
        self.parameter_output_values[self.result_details.name] = message
        self.publish_update_to_parameter(self.result_details.name, message)

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
        # If user has connected something to Failed output, they want to handle errors gracefully
        # in their workflow rather than crashing the entire process with an exception
        if not self._has_outgoing_connections(self.failure_output):
            raise ValueError(error_details) from exception

    def _has_outgoing_connections(self, parameter: Parameter) -> bool:
        """Check if a specific parameter has outgoing connections."""
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        connections = GriptapeNodes.FlowManager().get_connections()

        # Check if node has any outgoing connections
        node_connections = connections.outgoing_index.get(self.name)
        if node_connections is None:
            return False

        # Check if this specific parameter has any outgoing connections
        param_connections = node_connections.get(parameter.name, [])
        return len(param_connections) > 0
