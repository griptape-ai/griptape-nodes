from typing import Any, ClassVar

from griptape.artifacts import ImageUrlArtifact

from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.exe_types.node_types import BaseNode, DataNode
from griptape_nodes_library.utils.artifact_path_tethering import (
    ArtifactPathTethering,
    ArtifactTetheringConfig,
    default_extract_url_from_artifact_value,
)
from griptape_nodes_library.utils.image_utils import dict_to_image_url_artifact


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
        return super().after_value_set(parameter, value)


    def process(self) -> None:
        # Get parameter values and assign to outputs
        image_artifact = self.get_parameter_value("image")
        self.parameter_output_values["image"] = image_artifact

        path_value = self.get_parameter_value("path")
        self.parameter_output_values["path"] = path_value
