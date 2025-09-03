from typing import Any, ClassVar

from griptape.artifacts import ImageUrlArtifact

from griptape_nodes.exe_types.core_types import Parameter, ParameterMessage, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode, ControlNode
from griptape_nodes_library.three_d.three_d_artifact import ThreeDUrlArtifact
from griptape_nodes_library.utils.artifact_path_tethering import (
    ArtifactPathTethering,
    ArtifactTetheringConfig,
    default_extract_url_from_artifact_value,
)
from griptape_nodes_library.utils.three_d_utils import dict_to_three_d_url_artifact


class LoadThreeD(ControlNode):
    # Supported three_d file extensions
    SUPPORTED_EXTENSIONS: ClassVar[set[str]] = {".glb", ".gltf", ".stl", ".obj", ".fbx", ".ply", ".dae"}

    @staticmethod
    def _extract_url_from_three_d_value(three_d_value: Any) -> str | None:
        """Extract URL from three_d parameter value and strip query parameters."""
        return default_extract_url_from_artifact_value(artifact_value=three_d_value, artifact_classes=ThreeDUrlArtifact)

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        # Configuration for artifact tethering
        self._tethering_config = ArtifactTetheringConfig(
            dict_to_artifact_func=dict_to_three_d_url_artifact,
            extract_url_func=self._extract_url_from_three_d_value,
            supported_extensions=self.SUPPORTED_EXTENSIONS,
            default_extension="glb",
            url_content_type_prefix="model/",
        )

        self.three_d_parameter = Parameter(
            name="3d",
            input_types=["ThreeDArtifact", "ThreeDUrlArtifact", "str"],
            type="ThreeDUrlArtifact",
            output_type="ThreeDUrlArtifact",
            default_value=None,
            ui_options={
                "clickable_file_browser": True,
                "expander": True,
                "display_name": "3D File or path to 3D file",
            },
            tooltip="The 3D file that has been loaded.",
        )
        self.add_parameter(self.three_d_parameter)
        # Use the tethering utility to create the properly configured path parameter
        self.path_parameter = ArtifactPathTethering.create_path_parameter(
            name="path",
            config=self._tethering_config,
            display_name="File Path or URL",
            tooltip="Path to a local 3D file or URL to a 3D file",
        )
        self.add_parameter(self.path_parameter)

        # Tethering helper: keeps image and path parameters in sync bidirectionally
        # When user uploads a file -> path shows the URL, when user enters path -> image loads that file
        self._tethering = ArtifactPathTethering(
            node=self,
            artifact_parameter=self.three_d_parameter,
            path_parameter=self.path_parameter,
            config=self._tethering_config,
        )

        self.add_node_element(
            ParameterMessage(
                variant="none",
                name="help_message",
                value='To output an image of the model, click "Save Snapshot".',
                ui_options={"text_align": "text-center"},
            )
        )
        image_parameter = Parameter(
            name="image",
            type="ImageUrlArtifact",
            default_value=None,
            tooltip="The image of the 3D file.",
            allowed_modes={ParameterMode.PROPERTY, ParameterMode.OUTPUT},
        )
        self.add_parameter(image_parameter)

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

    def after_value_set(
        self,
        parameter: Parameter,
        value: Any,
    ) -> None:
        self._tethering.on_after_value_set(parameter, value)

        if parameter.name == "3d":
            # Handle both dictionary and artifact object types
            if isinstance(value, dict):
                # If value is a dictionary, use .get() method
                image_url = value.get("metadata", {}).get("imageUrl")
            elif hasattr(value, "meta") and hasattr(value.meta, "get"):
                # If value is an artifact object with metadata, access via .meta attribute
                image_url = value.meta.get("imageUrl")
            else:
                # No metadata available
                image_url = None

            if image_url:
                image_artifact = ImageUrlArtifact(value=image_url)
                self.set_parameter_value("image", image_artifact)
                self.parameter_output_values["image"] = image_artifact
                self.hide_message_by_name("help_message")
            else:
                self.show_message_by_name("help_message")

        return super().after_value_set(parameter, value)

    def process(self) -> None:
        three_d = self.get_parameter_value("3d")
        image = self.get_parameter_value("image")

        self.parameter_output_values["image"] = image
        self.parameter_output_values["3d"] = three_d
