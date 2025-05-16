import logging
from typing import Any

import cv2  # type: ignore[reportMissingImports]
import numpy as np
import PIL.Image
from griptape.artifacts import ImageUrlArtifact
from griptape.loaders import ImageLoader
from pillow_nodes_library.utils import (  # type: ignore[reportMissingImports]
    image_artifact_to_pil,  # type: ignore[reportMissingImports]
    pil_to_image_artifact,  # type: ignore[reportMissingImports]
)

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import AsyncResult, ControlNode
from griptape_nodes.retained_mode.retained_mode import RetainedMode as cmd  # noqa:  N813

logger = logging.getLogger("opencv_nodes_library")


class CannyConvertImage(ControlNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        self.add_parameter(
            Parameter(
                name="input_image",
                input_types=["ImageArtifact", "ImageUrlArtifact"],
                type="ImageArtifact",
                tooltip="input_image",
            )
        )
        self.add_parameter(
            Parameter(
                name="lower_threshold",
                default_value=50.0,
                input_types=["float"],
                type="float",
                tooltip="0 to 255 - The minimum intensity gradient that is considered as a possible edge.",
                ui_options={"slider": {"min_val": 0.0, "max_val": 255.0}, "step": 0.01},
            )
        )
        self.add_parameter(
            Parameter(
                name="upper_threshold",
                default_value=150.0,
                input_types=["float"],
                type="float",
                tooltip="0 to 255 - The strong edge gradient—pixels with values above this are definitely edges.",
                ui_options={"slider": {"min_val": 0.0, "max_val": 255.0}, "step": 0.01},
            )
        )
        self.add_parameter(
            Parameter(
                name="aperture_size",
                default_value=3,
                input_types=["int"],
                type="int",
                tooltip="aperture_size",
                ui_options={"slider": {"min_val": 3, "max_val": 7}, "step": 2},
            )
        )
        self.add_parameter(
            Parameter(
                name="l2_gradient",
                default_value=False,
                input_types=["bool"],
                type="bool",
                tooltip="l2_gradient",
            )
        )
        self.add_parameter(
            Parameter(
                name="output_image",
                output_type="ImageArtifact",
                tooltip="The output image",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

    def process(self) -> AsyncResult | None:
        yield lambda: self._process()

    def after_value_set(self, parameter: Parameter, value: Any, modified_parameters_set: set[str]) -> None:  # noqa: ARG002
        if parameter.name in {"output_image"}:
            return
        cmd.run_node(node_name=self.name)

    def _process(self) -> AsyncResult | None:
        input_image_artifact = self.get_parameter_value("input_image")
        lower_threshold = float(self.get_parameter_value("lower_threshold"))
        upper_threshold = float(self.get_parameter_value("upper_threshold"))
        aperture_size = int(self.get_parameter_value("aperture_size"))
        l2_gradient = bool(self.get_parameter_value("l2_gradient"))

        if isinstance(input_image_artifact, ImageUrlArtifact):
            input_image_artifact = ImageLoader().parse(input_image_artifact.to_bytes())

        input_image_pil = image_artifact_to_pil(input_image_artifact)

        # Convert Pillow image to grayscale NumPy array
        grayscale_input_image_np = np.array(input_image_pil.convert("L"))

        # Apply Canny edge detection
        edges = cv2.Canny(
            image=grayscale_input_image_np,
            threshold1=lower_threshold,
            threshold2=upper_threshold,
            apertureSize=aperture_size,
            L2gradient=l2_gradient,
        )

        # Convert NumPy result back to Pillow Image
        output_image_pil = PIL.Image.fromarray(edges)

        output_image_artifact = pil_to_image_artifact(output_image_pil)

        self.set_parameter_value("output_image", output_image_artifact)
        self.parameter_output_values["output_image"] = output_image_artifact
