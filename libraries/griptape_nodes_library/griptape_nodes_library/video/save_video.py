from pathlib import Path
from typing import Any

from griptape_nodes.exe_types.core_types import (
    Parameter,
    ParameterMode,
)
from griptape_nodes.exe_types.node_types import ControlNode
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes, logger
from griptape_nodes_library.utils.video_utils import detect_video_format, dict_to_video_url_artifact
from griptape_nodes_library.video.video_url_artifact import VideoUrlArtifact

DEFAULT_FILENAME = "griptape_nodes.mp4"


def to_video_artifact(video: Any | dict) -> Any:
    """Convert a video or a dictionary to a VideoArtifact."""
    if isinstance(video, dict):
        return dict_to_video_url_artifact(video)
    return video


def auto_determine_filename(base_filename: str, detected_format: str | None) -> str:
    """Auto-determine the output filename with the correct extension.

    Args:
        base_filename: The user-provided filename
        detected_format: The detected video format

    Returns:
        The filename with the appropriate extension
    """
    if detected_format is None:
        return base_filename

    # Get the base name without extension
    base_name = Path(base_filename).stem

    # If the user already provided an extension, keep it unless it's generic
    current_ext = Path(base_filename).suffix.lower()
    if current_ext and current_ext != ".mp4":  # Don't override if user specified non-default
        return base_filename

    # Use detected format
    return f"{base_name}.{detected_format}"


class SaveVideo(ControlNode):
    """Save a video to a file."""

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)

        # Add video input parameter
        self.add_parameter(
            Parameter(
                name="video",
                input_types=["VideoArtifact", "VideoUrlArtifact"],
                type="VideoUrlArtifact",
                allowed_modes={ParameterMode.INPUT},
                tooltip="The video to save to file",
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
                tooltip="The output filename. The file extension will be auto-determined from video format.",
            )
        )

    def _get_video_extension(self, video_value: Any) -> str | None:
        """Extract and return the file extension from video data."""
        if video_value is None:
            return None

        # Try to extract extension from VideoUrlArtifact URL
        if hasattr(video_value, "value") and isinstance(video_value.value, str):
            url = video_value.value
            filename_from_url = url.split("/")[-1].split("?")[0]
            if "." in filename_from_url:
                return Path(filename_from_url).suffix

        # Try to get extension from dict representation
        elif isinstance(video_value, dict) and "name" in video_value:
            filename = video_value["name"]
            if "." in filename:
                return Path(filename).suffix

        return None

    def after_incoming_connection(
        self, source_node: Any, source_parameter: Any, target_parameter: Any, modified_parameters_set: set[str]
    ) -> None:
        """Handle automatic extension detection when video connection is made."""
        if target_parameter.name == "video":
            # Get video value from the source node
            video_value = source_node.parameter_output_values.get(source_parameter.name)
            if video_value is None:
                video_value = source_node.parameter_values.get(source_parameter.name)

            extension = self._get_video_extension(video_value)
            if extension:
                current_output_path = self.get_parameter_value("output_path")
                new_filename = str(Path(current_output_path).with_suffix(extension))
                self.parameter_output_values["output_path"] = new_filename
                modified_parameters_set.add("output_path")
                logger.info(f"Updated extension to {extension}: {new_filename}")

        return super().after_incoming_connection(
            source_node, source_parameter, target_parameter, modified_parameters_set
        )

    def validate_before_workflow_run(self) -> list[Exception] | None:
        exceptions = []

        # Validate that we have a video.
        video = self.parameter_values.get("video")
        if not video:
            exceptions.append(ValueError("Video parameter is required"))

        return exceptions if exceptions else None

    def process(self) -> None:
        video = self.parameter_values.get("video")

        output_file = self.parameter_values.get("output_path", DEFAULT_FILENAME)

        try:
            # Detect video format before converting to artifact
            detected_format = detect_video_format(video)

            # Auto-determine filename with correct extension
            if detected_format:
                output_file = auto_determine_filename(output_file, detected_format)
                logger.debug(f"Auto-detected video format: {detected_format}, using filename: {output_file}")

            # Set output values BEFORE transforming to workspace-relative
            self.parameter_output_values["output_path"] = output_file

            video_artifact = to_video_artifact(video)

            if isinstance(video_artifact, VideoUrlArtifact):
                # For VideoUrlArtifact, we need to get the bytes from the URL
                # This might need adjustment based on how VideoUrlArtifact is implemented
                video_bytes = video_artifact.to_bytes()
            else:
                # Assume it has a value attribute with bytes
                video_bytes = video_artifact.value

            saved_path = GriptapeNodes.StaticFilesManager().save_static_file(video_bytes, output_file)

            success_msg = f"Saved video: {saved_path}"
            logger.info(success_msg)

        except Exception as e:
            error_message = str(e)
            msg = f"Error saving video: {error_message}"
            raise ValueError(msg) from e
