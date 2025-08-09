from typing import Any, ClassVar

from griptape.artifacts import ImageUrlArtifact

from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.exe_types.node_types import DataNode
from griptape_nodes.traits.file_system_picker import FileSystemPicker
from griptape_nodes_library.utils.artifact_path_tethering import (
    ArtifactPathTethering,
    ArtifactPathValidator,
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
            input_types=["ImageArtifact", "ImageUrlArtifact"],
            type="ImageArtifact",
            output_type="ImageUrlArtifact",
            default_value=None,
            ui_options={"clickable_file_browser": True, "expander": True, "edit_mask": True},
            tooltip="The loaded image.",
        )
        self.add_parameter(self.image_parameter)

        self.path_parameter = Parameter(
            name="path",
            input_types=["str"],
            type="str",
            default_value="",
            tooltip="Path to a local image file or URL to an image",
            ui_options={"display_name": "File Path or URL"},
        )

        self.path_parameter.add_trait(
            FileSystemPicker(
                allow_directories=False,
                allow_files=True,
                file_types=list(self.SUPPORTED_EXTENSIONS),
            )
        )

        self.path_parameter.add_trait(
            ArtifactPathValidator(supported_extensions=self.SUPPORTED_EXTENSIONS, url_content_type_prefix="image/")
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

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        # Delegate tethering logic to helper
        self._tethering.on_after_value_set(parameter, value)
        return super().after_value_set(parameter, value)

    def process(self) -> None:
        # Get outputs from tethering helper
        image_artifact = self._tethering.get_artifact_output()
        if image_artifact is not None:
            self.parameter_output_values["image"] = image_artifact

        self.parameter_output_values["path"] = self._tethering.get_path_output()
