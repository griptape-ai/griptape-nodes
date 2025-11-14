from io import BytesIO
from typing import Any

import httpx
from griptape.artifacts import ImageUrlArtifact
from PIL import Image

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode, DataNode
from griptape_nodes.exe_types.param_types.parameter_bool import ParameterBool
from griptape_nodes.exe_types.param_types.parameter_float import ParameterFloat
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes, logger
from griptape_nodes_library.utils.file_utils import generate_filename
from griptape_nodes_library.utils.image_utils import (
    apply_mask_transformations,
    dict_to_image_url_artifact,
    save_pil_image_with_named_filename,
)


class PaintMask(DataNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        self.add_parameter(
            Parameter(
                name="input_image",
                default_value=None,
                input_types=["ImageArtifact", "ImageUrlArtifact"],
                output_type="ImageArtifact",
                type="ImageArtifact",
                tooltip="The image to display",
                ui_options={"hide_property": True},
                allowed_modes={ParameterMode.INPUT},
            )
        )

        self.add_parameter(
            Parameter(
                name="output_mask",
                input_types=["ImageArtifact", "ImageUrlArtifact"],
                type="ImageUrlArtifact",
                tooltip="Generated mask image.",
                ui_options={"expander": True, "edit_mask": True, "edit_mask_paint_mask": True},
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.OUTPUT},
            )
        )
        self.add_parameter(ParameterBool(name="invert_mask", default_value=False))
        self.add_parameter(ParameterFloat(name="grow_shrink", default_value=0, slider=True, min_val=-100, max_val=100))
        self.add_parameter(ParameterFloat(name="blur_mask", default_value=0, slider=True, min_val=-0, max_val=100))

        self.add_parameter(
            Parameter(
                name="output_image",
                input_types=["ImageArtifact", "ImageUrlArtifact"],
                type="ImageUrlArtifact",
                tooltip="Final image with mask applied.",
                ui_options={"expander": True},
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

    def process(self) -> None:
        # Get input image
        input_image = self.get_parameter_value("input_image")

        if input_image is None:
            return

        # Normalize dict input to ImageUrlArtifact
        if isinstance(input_image, dict):
            input_image = dict_to_image_url_artifact(input_image)

        # Check if we need to generate a new mask
        if self._needs_mask_regeneration(input_image):
            # Generate mask (extract alpha channel)
            mask_pil = self.generate_initial_mask(input_image)

            # Save mask to static folder
            mask_buffer = BytesIO()
            mask_pil.save(mask_buffer, format="PNG")
            mask_buffer.seek(0)
            mask_filename = generate_filename(
                node_name=self.name,
                suffix="_mask",
                extension="png",
            )
            mask_url = GriptapeNodes.StaticFilesManager().save_static_file(mask_buffer.getvalue(), mask_filename)

            # Create ImageUrlArtifact directly with source_image_url in meta
            mask_artifact = ImageUrlArtifact(mask_url, meta={"source_image_url": input_image.value})

            # Set output mask
            self.parameter_output_values["output_mask"] = mask_artifact

        # Get the current mask
        mask_artifact = self.get_parameter_value("output_mask")
        if mask_artifact is not None:
            # Apply the mask to input image
            self._apply_mask_to_input(input_image, mask_artifact)

    def after_incoming_connection(
        self,
        source_node: BaseNode,
        source_parameter: Parameter,
        target_parameter: Parameter,
    ) -> None:
        """Handle input connections and update outputs accordingly."""
        if target_parameter.name == "input_image":
            input_image = self.get_parameter_value("input_image")
            if input_image is not None:
                self._handle_input_image_change(input_image)

        return super().after_incoming_connection(source_node, source_parameter, target_parameter)

    def _handle_input_image_change(self, value: Any) -> None:
        # Normalize input image to ImageUrlArtifact if needed
        image_artifact = value
        if isinstance(value, dict):
            image_artifact = dict_to_image_url_artifact(value)

        # Check and see if the output_mask is set
        output_mask_value = self.get_parameter_value("output_mask")
        if output_mask_value is None:
            self._create_new_mask(image_artifact)
        else:
            self._update_existing_mask(output_mask_value, image_artifact)

    def _create_new_mask(self, image_artifact: ImageUrlArtifact) -> None:
        output_mask_value = self.generate_initial_mask(image_artifact)
        mask_buffer = BytesIO()
        output_mask_value.save(mask_buffer, format="PNG")
        mask_buffer.seek(0)
        mask_filename = generate_filename(
            node_name=self.name,
            suffix="_mask",
            extension="png",
        )
        mask_url = GriptapeNodes.StaticFilesManager().save_static_file(mask_buffer.getvalue(), mask_filename)
        output_mask_artifact = ImageUrlArtifact(mask_url, meta={"source_image_url": image_artifact.value})
        self.set_parameter_value("output_mask", output_mask_artifact)
        self.set_parameter_value("output_image", image_artifact)

    def _update_existing_mask(self, output_mask_value: Any, image_artifact: ImageUrlArtifact) -> None:
        # If we have a dict representation, check if it's been edited
        if isinstance(output_mask_value, dict):
            if "meta" not in output_mask_value:
                output_mask_value["meta"] = {}
            output_mask_value["meta"]["source_image_url"] = image_artifact.value
            self.set_parameter_value("output_mask", output_mask_value)
        else:
            # For ImageUrlArtifact, check if it's been edited
            meta = getattr(output_mask_value, "meta", {})
            if isinstance(meta, dict) and meta.get("maskEdited", False):
                # If mask was edited, keep it but update source image URL
                mask_url = output_mask_value.value
                response = httpx.get(mask_url, timeout=30)
                response.raise_for_status()
                mask_content = response.content
                new_mask_filename = generate_filename(
                    node_name=self.name,
                    suffix="_mask",
                    extension="png",
                )
                mask_url = GriptapeNodes.StaticFilesManager().save_static_file(mask_content, new_mask_filename)
                mask_artifact = ImageUrlArtifact(
                    mask_url, meta={"source_image_url": image_artifact.value, "maskEdited": True}
                )
                self.set_parameter_value("output_mask", mask_artifact)
            else:
                # If mask wasn't edited, generate a new one
                self._create_new_mask(image_artifact)
                return

            self._apply_mask_to_input(image_artifact, mask_artifact)

    def _handle_output_mask_change(self, value: Any) -> None:
        input_image = self.get_parameter_value("input_image")
        if input_image is not None:
            if isinstance(input_image, dict):
                input_image = dict_to_image_url_artifact(input_image)
            if isinstance(value, dict):
                mask_url = value.get("value")
                if mask_url:
                    mask_artifact = ImageUrlArtifact(
                        mask_url, meta={"source_image_url": input_image.value, "maskEdited": True}
                    )
                    self.set_parameter_value("output_mask", mask_artifact)
                    value = mask_artifact
            self._apply_mask_to_input(input_image, value)

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        if parameter.name == "input_image" and value is not None:
            self._handle_input_image_change(value)
        elif parameter.name == "output_mask" and value is not None:
            self._handle_output_mask_change(value)
        elif parameter.name in ["invert_mask", "grow_shrink", "blur_mask"]:
            # When transform parameters change, re-apply the current mask
            input_image = self.get_parameter_value("input_image")
            mask_artifact = self.get_parameter_value("output_mask")

            if input_image is None or mask_artifact is None:
                msg = f"{self.name}: Input image or mask is not set, skipping mask application"
                logger.debug(msg)
                return super().after_value_set(parameter, value)

            if isinstance(input_image, dict):
                input_image = dict_to_image_url_artifact(input_image)

            self._apply_mask_to_input(input_image, mask_artifact)

        return super().after_value_set(parameter, value)

    def _needs_mask_regeneration(self, input_image: ImageUrlArtifact) -> bool:
        """Check if mask needs to be regenerated based on mask editing status and source image."""
        # Get current output mask
        output_mask = self.get_parameter_value("output_mask")

        if output_mask is None:
            # No mask exists, need to generate one
            return True

        # Check if the mask has been manually edited
        if isinstance(output_mask, dict):
            # Handle dict representation
            if output_mask.get("meta", {}).get("maskEdited", False):
                return False
            # Check if source image has changed
            stored_source_url = output_mask.get("meta", {}).get("source_image_url")
        else:
            # Handle ImageUrlArtifact with meta attribute
            meta = getattr(output_mask, "meta", {})
            if isinstance(meta, dict) and meta.get("maskEdited", False):
                return False
            # Check if source image has changed
            stored_source_url = meta.get("source_image_url") if isinstance(meta, dict) else None

        # If source image URL has changed, regenerate mask
        return stored_source_url != input_image.value

    def generate_initial_mask(self, image_artifact: ImageUrlArtifact) -> Image.Image:
        """Extract the alpha channel from a URL-based image."""
        pil_image = self.load_pil_from_url(image_artifact.value).convert("RGBA")
        # Create a grayscale mask from alpha channel
        mask = pil_image.getchannel("A")
        # Resize mask to match input image size
        mask = mask.resize(pil_image.size, Image.Resampling.NEAREST)
        # Convert to RGB like outpaint_image.py does
        return mask.convert("RGB")

    def load_pil_from_url(self, url: str) -> Image.Image:
        """Load image from URL using httpx."""
        response = httpx.get(url, timeout=30)
        response.raise_for_status()
        return Image.open(BytesIO(response.content))

    def _extract_alpha_from_mask(self, mask_pil: Image.Image) -> Image.Image:
        """Extract red channel from mask image to use as alpha channel."""
        if mask_pil.mode == "L":
            # Grayscale mode - use directly (no conversion needed)
            return mask_pil
        if mask_pil.mode == "RGB":
            r, _, _ = mask_pil.split()
            return r
        if mask_pil.mode == "RGBA":
            r, _, _, _ = mask_pil.split()
            return r

        # For other modes, convert to RGB first
        mask_pil = mask_pil.convert("RGB")
        r, _, _ = mask_pil.split()
        return r

    def _apply_mask_to_input(self, input_image: ImageUrlArtifact, mask_artifact: Any) -> None:
        """Apply mask to input image using red channel as alpha and set as output_image."""
        # Load input image
        input_pil = self.load_pil_from_url(input_image.value).convert("RGBA")

        # Process the mask
        if isinstance(mask_artifact, dict):
            mask_artifact = dict_to_image_url_artifact(mask_artifact)

        # Load mask and extract alpha channel
        mask_pil = self.load_pil_from_url(mask_artifact.value)
        alpha = self._extract_alpha_from_mask(mask_pil)

        # Resize alpha to match input image size
        alpha = alpha.resize(input_pil.size, Image.Resampling.NEAREST)

        # Apply mask transformations
        grow_shrink = self.get_parameter_value("grow_shrink")
        invert_mask = self.get_parameter_value("invert_mask")
        blur_mask = self.get_parameter_value("blur_mask")
        alpha = apply_mask_transformations(
            alpha,
            grow_shrink=grow_shrink,
            invert=invert_mask,
            blur_radius=blur_mask,
            context_name=self.name,
        )

        # Apply alpha channel to input image
        input_pil.putalpha(alpha)

        # Save output image with deterministic filename (overwrites same file)
        output_filename = generate_filename(
            node_name=self.name,
            suffix="_output",
            extension="png",
        )
        output_artifact = save_pil_image_with_named_filename(input_pil, output_filename)
        self.set_parameter_value("output_image", output_artifact)
