from typing import Any, ClassVar

from griptape.artifacts import ImageUrlArtifact

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode, DataNode
from griptape_nodes.retained_mode.griptape_nodes import logger
from griptape_nodes_library.utils.artifact_path_tethering import (
    ArtifactPathTethering,
    ArtifactTetheringConfig,
    default_extract_url_from_artifact_value,
)
from griptape_nodes_library.utils.file_utils import generate_filename
from griptape_nodes_library.utils.image_utils import (
    dict_to_image_url_artifact,
    extract_channel_from_image,
    load_pil_from_url,
    save_pil_image_with_named_filename,
)


class LoadImage(DataNode):
    # Supported image file extensions
    SUPPORTED_EXTENSIONS: ClassVar[set[str]] = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"}

    @staticmethod
    def _extract_url_from_image_value(image_value: Any) -> str | None:
        """Extract URL from image parameter value and strip query parameters."""
        return default_extract_url_from_artifact_value(artifact_value=image_value, artifact_classes=ImageUrlArtifact)

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        # Configuration for artifact tethering
        self._tethering_config = ArtifactTetheringConfig(
            dict_to_artifact_func=dict_to_image_url_artifact,
            extract_url_func=self._extract_url_from_image_value,
            supported_extensions=self.SUPPORTED_EXTENSIONS,
            default_extension="png",
            url_content_type_prefix="image/",
        )
        self.image_parameter = Parameter(
            name="image",
            input_types=["ImageUrlArtifact", "ImageArtifact", "str"],
            type="ImageUrlArtifact",
            output_type="ImageUrlArtifact",
            default_value=None,
            ui_options={
                "clickable_file_browser": True,
                "expander": True,
                "edit_mask": True,
                "display_name": "Image or Path to Image",
            },
            tooltip="The loaded image.",
        )
        self.add_parameter(self.image_parameter)

        # Use the tethering utility to create the properly configured path parameter
        self.path_parameter = ArtifactPathTethering.create_path_parameter(
            name="path",
            config=self._tethering_config,
            display_name="File Path or URL",
            tooltip="Path to a local image file or URL to an image",
        )
        self.add_parameter(self.path_parameter)

        # Tethering helper: keeps image and path parameters in sync bidirectionally
        # When user uploads a file -> path shows the URL, when user enters path -> image loads that file
        self._tethering = ArtifactPathTethering(
            node=self,
            artifact_parameter=self.image_parameter,
            path_parameter=self.path_parameter,
            config=self._tethering_config,
        )

        # Add channel parameter for mask extraction
        from griptape_nodes.traits.options import Options

        channel_param = Parameter(
            name="mask_channel",
            type="str",
            tooltip="Channel to extract as mask (red, green, blue, or alpha).",
            default_value="alpha",
            ui_options={"hide": True},
        )
        channel_param.add_trait(Options(choices=["red", "green", "blue", "alpha"]))
        self.add_parameter(channel_param)

        self.add_parameter(
            Parameter(
                name="output_mask",
                type="ImageUrlArtifact",
                tooltip="The Mask for the image",
                ui_options={"expander": True, "hide": True},
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

    def after_incoming_connection(
        self,
        source_node: BaseNode,
        source_parameter: Parameter,
        target_parameter: Parameter,
    ) -> None:
        # Delegate to tethering helper - only artifact parameter can receive connections
        self._tethering.on_incoming_connection(target_parameter)
        return super().after_incoming_connection(source_node, source_parameter, target_parameter)

    def after_incoming_connection_removed(
        self,
        source_node: BaseNode,
        source_parameter: Parameter,
        target_parameter: Parameter,
    ) -> None:
        # Delegate to tethering helper - only artifact parameter can have connections removed
        self._tethering.on_incoming_connection_removed(target_parameter)
        return super().after_incoming_connection_removed(source_node, source_parameter, target_parameter)

    def before_value_set(self, parameter: Parameter, value: Any) -> Any:
        # Delegate to tethering helper for dynamic settable control
        return self._tethering.on_before_value_set(parameter, value)

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        # Delegate tethering logic to helper for value synchronization and settable restoration
        self._tethering.on_after_value_set(parameter, value)

        # Handle mask extraction when image or mask_channel changes
        if parameter.name in ["image", "mask_channel"] and value is not None:
            self._extract_mask_if_possible()

        return super().after_value_set(parameter, value)

    def process(self) -> None:
        # Get parameter values and assign to outputs
        image_artifact = self.get_parameter_value("image")
        self.parameter_output_values["image"] = image_artifact

        path_value = self.get_parameter_value("path")
        self.parameter_output_values["path"] = path_value

        # Extract mask if image is available
        self._extract_mask_if_possible()

    def _extract_mask_if_possible(self) -> None:
        """Extract mask from the loaded image if both image and channel are available."""
        image_artifact = self.get_parameter_value("image")
        mask_channel = self.get_parameter_value("mask_channel")

        if image_artifact is None or mask_channel is None:
            return

        # Normalize input to ImageUrlArtifact
        if isinstance(image_artifact, dict):
            image_artifact = dict_to_image_url_artifact(image_artifact)

        self._extract_channel_as_mask(image_artifact, mask_channel)

    def _extract_channel_as_mask(self, image_artifact: ImageUrlArtifact, channel: str) -> None:
        """Extract a channel from the input image and set as mask output."""
        try:
            # Load image
            image_pil = load_pil_from_url(image_artifact.value)

            # Extract the specified channel as mask
            mask = extract_channel_from_image(image_pil, channel, "image")

            # Save output mask and create URL artifact with proper filename
            filename = self._generate_filename_with_suffix("_load_mask", "png")
            output_artifact = save_pil_image_with_named_filename(mask, filename, "PNG")
            self.set_parameter_value("output_mask", output_artifact)
            self.publish_update_to_parameter("output_mask", output_artifact)

        except Exception as e:
            logger.warning(f"{self.name}: Error extracting mask: {e}")

    def _generate_filename_with_suffix(self, suffix: str, extension: str) -> str:
        """Generate a meaningful filename based on workflow and node information."""
        return generate_filename(
            node_name=self.name,
            suffix=suffix,
            extension=extension,
        )
