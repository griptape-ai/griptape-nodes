import logging
from typing import Any, ClassVar

import cv2  # type: ignore[reportMissingImports]
import numpy as np
import PIL.Image
from griptape.artifacts import ImageUrlArtifact
from pillow_nodes_library.utils import image_artifact_to_pil, pil_to_image_artifact
from utils.image_utils import load_image_from_url_artifact

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import AsyncResult, ControlNode
from griptape_nodes.retained_mode.retained_mode import RetainedMode as cmd  # noqa:  N813
from griptape_nodes.traits.options import Options

logger = logging.getLogger("opencv_nodes_library")


class MorphologyImage(ControlNode):
    """Apply OpenCV morphological operations to grayscale images.

    Supports the four fundamental morphological operations:
    - Erode: Erodes away the boundaries of foreground objects
    - Dilate: Expands the boundaries of foreground objects
    - Open: Erosion followed by dilation (removes noise)
    - Close: Dilation followed by erosion (closes small holes)

    All operations use structuring elements (kernels) with configurable
    shape, size, and iteration count.
    """

    # Morphological operations
    OPERATIONS: ClassVar[list[str]] = ["Erode", "Dilate", "Open", "Close"]
    DEFAULT_OPERATION = "Erode"

    # Kernel shapes
    KERNEL_SHAPES: ClassVar[list[str]] = ["Rectangle", "Ellipse", "Cross"]
    DEFAULT_KERNEL_SHAPE = "Rectangle"

    # Parameter constants
    MIN_KERNEL_SIZE = 3
    MAX_KERNEL_SIZE = 25
    DEFAULT_KERNEL_SIZE = 5

    MIN_ITERATIONS = 1
    MAX_ITERATIONS = 10
    DEFAULT_ITERATIONS = 1

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        self.add_parameter(
            Parameter(
                name="input_image",
                input_types=["ImageArtifact", "ImageUrlArtifact"],
                type="ImageArtifact",
                tooltip="Input image to process",
            )
        )
        self.add_parameter(
            Parameter(
                name="operation",
                default_value=self.DEFAULT_OPERATION,
                input_types=["str"],
                type="str",
                tooltip="Select the morphological operation to apply",
                traits={Options(choices=self.OPERATIONS)},
            )
        )
        self.add_parameter(
            Parameter(
                name="kernel_shape",
                default_value=self.DEFAULT_KERNEL_SHAPE,
                input_types=["str"],
                type="str",
                tooltip="Select the shape of the structuring element (kernel)",
                traits={Options(choices=self.KERNEL_SHAPES)},
            )
        )
        self.add_parameter(
            Parameter(
                name="kernel_size",
                default_value=self.DEFAULT_KERNEL_SIZE,
                input_types=["int"],
                type="int",
                tooltip=f"Size of the structuring element ({self.MIN_KERNEL_SIZE}-{self.MAX_KERNEL_SIZE}, must be odd)",
                ui_options={"slider": {"min_val": self.MIN_KERNEL_SIZE, "max_val": self.MAX_KERNEL_SIZE}},
            )
        )
        self.add_parameter(
            Parameter(
                name="iterations",
                default_value=self.DEFAULT_ITERATIONS,
                input_types=["int"],
                type="int",
                tooltip=f"Number of times to apply the operation ({self.MIN_ITERATIONS}-{self.MAX_ITERATIONS})",
                ui_options={"slider": {"min_val": self.MIN_ITERATIONS, "max_val": self.MAX_ITERATIONS}},
            )
        )
        self.add_parameter(
            Parameter(
                name="output_image",
                output_type="ImageUrlArtifact",
                tooltip="The output image",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

    def process(self) -> AsyncResult | None:
        yield lambda: self._process()

    def after_value_set(self, parameter: Parameter, _value: Any) -> None:
        """Process image automatically when parameters change for live preview."""
        # Process when Morphology parameters change and an input image exists
        if (
            parameter.name in {"operation", "kernel_shape", "kernel_size", "iterations"}
            and self.get_parameter_value("input_image") is not None
        ):
            cmd.run_node(node_name=self.name)

    def _get_opencv_operation(self, operation: str) -> int:
        """Map operation name to OpenCV constant."""
        operation_map = {
            "Erode": cv2.MORPH_ERODE,
            "Dilate": cv2.MORPH_DILATE,
            "Open": cv2.MORPH_OPEN,
            "Close": cv2.MORPH_CLOSE,
        }
        return operation_map.get(operation, cv2.MORPH_ERODE)

    def _get_opencv_kernel_shape(self, shape: str) -> int:
        """Map kernel shape name to OpenCV constant."""
        shape_map = {
            "Rectangle": cv2.MORPH_RECT,
            "Ellipse": cv2.MORPH_ELLIPSE,
            "Cross": cv2.MORPH_CROSS,
        }
        return shape_map.get(shape, cv2.MORPH_RECT)

    def _process(self) -> AsyncResult | None:
        input_image_artifact = self.get_parameter_value("input_image")
        operation = str(self.get_parameter_value("operation"))
        kernel_shape = str(self.get_parameter_value("kernel_shape"))
        kernel_size = int(self.get_parameter_value("kernel_size"))
        iterations = int(self.get_parameter_value("iterations"))

        if kernel_size % 2 == 0:
            kernel_size += 1
            logger.warning("%s: Kernel size adjusted to odd number: %s", self.name, kernel_size)

        logger.debug(
            "%s: Processing with operation=%s, kernel_shape=%s, kernel_size=%s, iterations=%s",
            self.name,
            operation,
            kernel_shape,
            kernel_size,
            iterations,
        )

        if isinstance(input_image_artifact, ImageUrlArtifact):
            input_image_artifact = load_image_from_url_artifact(input_image_artifact)

        input_image_pil = image_artifact_to_pil(input_image_artifact)

        # Convert Pillow image to grayscale NumPy array
        grayscale_input_image_np = np.array(input_image_pil.convert("L"))

        # Get kernel and apply morphological operation
        cv_kernel_shape = self._get_opencv_kernel_shape(kernel_shape)
        kernel = cv2.getStructuringElement(cv_kernel_shape, (kernel_size, kernel_size))

        cv_operation = self._get_opencv_operation(operation)
        result = cv2.morphologyEx(grayscale_input_image_np, cv_operation, kernel, iterations=iterations)

        # Convert NumPy result back to Pillow Image
        output_image_pil = PIL.Image.fromarray(result, mode="L")

        output_image_artifact = pil_to_image_artifact(output_image_pil)

        self.set_parameter_value("output_image", output_image_artifact)
        self.parameter_output_values["output_image"] = output_image_artifact
