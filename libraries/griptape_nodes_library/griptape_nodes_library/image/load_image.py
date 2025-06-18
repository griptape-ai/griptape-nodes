import base64
import uuid
from typing import Any

import httpx
from griptape.artifacts import ImageArtifact, ImageUrlArtifact
from griptape.loaders import ImageLoader

from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.exe_types.node_types import DataNode
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes, logger
from griptape_nodes_library.utils.image_utils import add_image_metadata


class LoadImage(DataNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        # Need to define the category
        self.category = "Image"
        self.description = "Load an image"
        image_parameter = Parameter(
            name="image",
            input_types=["ImageArtifact", "ImageUrlArtifact"],
            type="ImageArtifact",
            output_type="ImageUrlArtifact",
            default_value=None,
            ui_options={"clickable_file_browser": True, "expander": True, "edit_mask": True},
            tooltip="The image that has been generated.",
        )
        self.add_parameter(image_parameter)
        # Add input parameter for model selection

    def _to_image_artifact(self, image: Any) -> Any:
        logger.info("Starting _to_image_artifact")
        if isinstance(image, dict):
            logger.info("Image is a dict")
            # If it's already an ImageUrlArtifact, we still need to add metadata
            if image["type"] == "ImageUrlArtifact":
                logger.info("Image is an ImageUrlArtifact")
                # Get the image bytes from the URL
                try:
                    logger.info("Getting image bytes from URL")
                    image_bytes = httpx.get(image["value"], timeout=30).content
                    # Create temporary ImageArtifact to add metadata
                    temp_artifact = ImageLoader().parse(image_bytes)
                    logger.info("Adding metadata to ImageArtifact")
                    add_image_metadata(temp_artifact, image_bytes)
                    logger.info("Saving image to static file")
                    # Create new URL artifact with metadata
                    url = GriptapeNodes.StaticFilesManager().save_static_file(image_bytes, f"{uuid.uuid4()}.png")
                    logger.info("Returning ImageUrlArtifact with metadata: %s", temp_artifact.meta)
                    return ImageUrlArtifact(url, meta=temp_artifact.meta)
                except Exception as e:
                    logger.error("Failed to load image from URL: %s", e)
                    # If we can't load the image, preserve existing metadata
                    meta = image.get("meta", {})
                    return ImageUrlArtifact(image["value"], meta=meta)

            # For other image types, create a new ImageUrlArtifact with metadata
            value = image["value"]
            if "base64," in value:
                value = value.split("base64,")[1]

            image_bytes = base64.b64decode(value)

            # Create temporary ImageArtifact to add metadata
            temp_artifact = ImageLoader().parse(image_bytes)
            logger.info("Adding metadata to ImageArtifact")
            add_image_metadata(temp_artifact, image_bytes)
            logger.info("Metadata added: %s", temp_artifact.meta)

            # Save to static file and create URL artifact with metadata
            url = GriptapeNodes.StaticFilesManager().save_static_file(image_bytes, f"{uuid.uuid4()}.png")
            logger.info("Returning ImageUrlArtifact with metadata: %s", temp_artifact.meta)
            return ImageUrlArtifact(url, meta=temp_artifact.meta)
        if isinstance(image, ImageArtifact):
            logger.info("Image is an ImageArtifact")
            # If it's an ImageArtifact, add metadata and convert to URL artifact
            logger.info("Adding metadata to ImageArtifact")
            add_image_metadata(image, image.value)
            logger.info("Metadata added: %s", image.meta)
            url = GriptapeNodes.StaticFilesManager().save_static_file(image.value, f"{uuid.uuid4()}.png")
            logger.info("Returning ImageUrlArtifact with metadata: %s", image.meta)
            return ImageUrlArtifact(url, meta=image.meta)
        if isinstance(image, ImageUrlArtifact):
            logger.info("Image is an ImageUrlArtifact")
            # If it's already an ImageUrlArtifact, we still need to add metadata
            try:
                logger.info("Getting image bytes from URL")
                image_bytes = image.to_bytes()
                # Create temporary ImageArtifact to add metadata
                temp_artifact = ImageLoader().parse(image_bytes)
                logger.info("Adding metadata to ImageArtifact")
                add_image_metadata(temp_artifact, image_bytes)
                logger.info("Metadata added: %s", temp_artifact.meta)
                # Create new URL artifact with metadata
                url = GriptapeNodes.StaticFilesManager().save_static_file(image_bytes, f"{uuid.uuid4()}.png")
                logger.info("Returning ImageUrlArtifact with metadata: %s", temp_artifact.meta)
                return ImageUrlArtifact(url, meta=temp_artifact.meta)
            except Exception as e:
                logger.error("Failed to load image from URL: %s", e)
                # If we can't load the image, preserve existing metadata
                return image

        return image

    def after_value_set(self, parameter: Parameter, value: Any, modified_parameters_set: set[str]) -> None:
        if parameter.name == "image":
            logger.info("Image value changed, updating metadata")
            image_artifact = self._to_image_artifact(value)
            logger.info("New image artifact with metadata: %s", image_artifact.meta)
            self.parameter_output_values["image"] = image_artifact
        return super().after_value_set(parameter, value, modified_parameters_set)

    def process(self) -> None:
        image = self.get_parameter_value("image")
        image_artifact = self._to_image_artifact(image)
        self.parameter_output_values["image"] = image_artifact
