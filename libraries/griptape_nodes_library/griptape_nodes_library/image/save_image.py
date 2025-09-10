from enum import StrEnum, auto
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
from griptape_nodes.traits.button import Button
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
                traits={Button(label="save")},
            )
        )

        # Advanced parameters in a collapsible ParameterGroup
        with ParameterGroup(name="Advanced") as group:
            group.ui_options = {"collapsed": True}

            # Boolean parameter to indicate success/failure
            self.was_successful = Parameter(
                name="was_successful",
                tooltip="Indicates whether it completed without errors.",
                type="bool",
                default_value=False,
                allowed_modes={ParameterMode.OUTPUT},
            )

            # Result details parameter with multiline option
            self.result_details = Parameter(
                name="result_details",
                tooltip="Details about the image save operation result",
                type="str",
                default_value="",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.OUTPUT},
                settable=False,
                ui_options={"multiline": True},
            )

        self.add_node_element(group)

        # Track execution state for control flow routing
        self._execution_succeeded: bool | None = None

    def process(self) -> None:
        # Reset execution state and result details at the start of each run
        self._execution_succeeded = None
        self._assign_result_details("")
        self.set_parameter_value(self.was_successful.name, False)

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
                self._handle_execution_result(
                    status=SaveImageStatus.FAILURE,
                    saved_path="",
                    input_info=input_info,
                    output_file=output_file,
                    details=error_details,
                    exception=e,
                )
                raise ValueError(error_details) from e

        # Convert to appropriate artifact type
        try:
            image_artifact = to_image_artifact(processed_image)
        except Exception as e:
            error_details = f"Failed to convert image to artifact: {e!s}"
            self._handle_execution_result(
                status=SaveImageStatus.FAILURE,
                saved_path="",
                input_info=input_info,
                output_file=output_file,
                details=error_details,
                exception=e,
            )
            raise ValueError(error_details) from e

        # Save to static storage
        try:
            saved_path = GriptapeNodes.StaticFilesManager().save_static_file(image_artifact.to_bytes(), output_file)
        except Exception as e:
            error_details = f"Failed to save image to static storage: {e!s}"
            self._handle_execution_result(
                status=SaveImageStatus.FAILURE,
                saved_path="",
                input_info=input_info,
                output_file=output_file,
                details=error_details,
                exception=e,
            )
            raise ValueError(error_details) from e

        # Success case
        success_details = "Image saved successfully"
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
                self.set_parameter_value(self.was_successful.name, False)

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
                self.set_parameter_value(self.was_successful.name, True)

                result_details = (
                    f"No image to save (warning)\n"
                    f"Input: {input_info}\n"
                    f"Requested filename: {output_file}\n"
                    f"Result: No file created"
                )

                self._assign_result_details(f"{status}: {result_details}")

            case SaveImageStatus.SUCCESS:
                self._execution_succeeded = True
                self.set_parameter_value(self.was_successful.name, True)

                result_details = (
                    f"Image saved successfully\n"
                    f"Input: {input_info}\n"
                    f"Requested filename: {output_file}\n"
                    f"Saved to: {saved_path}"
                )

                self._assign_result_details(f"{status}: {result_details}")

    def _assign_result_details(self, message: str) -> None:
        """Helper to assign result_details using publish_update_to_parameter."""
        self.parameter_output_values[self.result_details.name] = message
        self.publish_update_to_parameter(self.result_details.name, message)
