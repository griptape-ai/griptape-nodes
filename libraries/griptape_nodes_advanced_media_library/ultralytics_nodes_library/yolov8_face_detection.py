import io
import logging
from dataclasses import dataclass
from typing import Any

import PIL.Image
from diffusers_nodes_library.common.utils.huggingface_utils import model_cache
from griptape.artifacts import ImageUrlArtifact
from supervision import Detections  # type: ignore[import-untyped]
from utils.image_utils import load_image_from_url_artifact

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import AsyncResult, ControlNode, NodeResolutionState
from ultralytics_nodes_library.yolov8_face_detection_parameters import (
    YOLOv8FaceDetectionParameters,
)

logger = logging.getLogger("ultralytics_nodes_library")


@dataclass
class BoundingBox:
    """Represents a bounding box with position and dimensions."""

    x: int
    y: int
    width: int
    height: int


class YOLOv8FaceDetection(ControlNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.params = YOLOv8FaceDetectionParameters(self)
        self.params.add_input_parameters()

        self.add_parameter(
            Parameter(
                name="input_image",
                input_types=["ImageArtifact", "ImageUrlArtifact"],
                type="ImageArtifact",
                tooltip="Input image for face detection",
            )
        )

        self.add_parameter(
            Parameter(
                name="detected_faces",
                output_type="list",
                tooltip="List of detected faces with bounding boxes and confidence scores",
                allowed_modes={ParameterMode.OUTPUT},
                ui_options={"multiline": True},
            )
        )

        self.params.add_logs_output_parameter()

    @property
    def state(self) -> NodeResolutionState:
        """Overrides BaseNode.state @property to compute state based on model's existence in model_cache, ensuring model rebuild if missing."""
        if self._state == NodeResolutionState.RESOLVED and not model_cache.has_pipeline(self.params.get_cache_key()):
            logger.debug("Model not found in cache, marking node as UNRESOLVED")
            return NodeResolutionState.UNRESOLVED
        return super().state

    @state.setter
    def state(self, new_state: NodeResolutionState) -> None:
        self._state = new_state

    def validate_before_node_run(self) -> list[Exception] | None:
        errors = self.params.validate_before_node_run()

        if not self.get_parameter_value("input_image"):
            if errors is None:
                errors = []
            errors.append(Exception("No input image provided"))

        return errors or None

    def _dilate_bbox(self, bbox: BoundingBox, dilation_percent: float, img_width: int, img_height: int) -> BoundingBox:
        """Dilate bounding box by percentage while keeping it centered.

        Args:
            bbox: Original bounding box
            dilation_percent: Percentage to expand (e.g., 10 for 10%)
            img_width: Image width for boundary clamping
            img_height: Image height for boundary clamping

        Returns:
            New BoundingBox with dilated dimensions
        """
        # Calculate dilation factor (e.g., 10% -> 1.10)
        dilation_factor = 1.0 + (dilation_percent / 100.0)

        # Calculate new dimensions
        new_width = int(bbox.width * dilation_factor)
        new_height = int(bbox.height * dilation_factor)

        # Calculate offsets to keep box centered
        width_offset = (new_width - bbox.width) // 2
        height_offset = (new_height - bbox.height) // 2

        # Calculate new position
        new_x = bbox.x - width_offset
        new_y = bbox.y - height_offset

        # Clamp to image boundaries
        new_x = max(0, min(new_x, img_width - new_width))
        new_y = max(0, min(new_y, img_height - new_height))

        # Ensure width and height don't exceed image boundaries
        new_width = min(new_width, img_width - new_x)
        new_height = min(new_height, img_height - new_y)

        return BoundingBox(x=new_x, y=new_y, width=new_width, height=new_height)

    def process(self) -> AsyncResult | None:
        self.append_value_to_parameter("logs", "Loading YOLOv8 face detection model...\n")

        cache_key = self.params.get_cache_key()
        builder = self.params.get_model_builder()

        model = yield lambda: model_cache.get_or_build_pipeline(cache_key, builder)

        self.append_value_to_parameter("logs", "Model loading complete.\n")

        yield lambda: self._process(model)

    def _process(self, model: Any) -> AsyncResult | None:
        input_image_artifact = self.get_parameter_value("input_image")

        # Convert ImageUrlArtifact to ImageArtifact if needed
        if isinstance(input_image_artifact, ImageUrlArtifact):
            input_image_artifact = load_image_from_url_artifact(input_image_artifact)

        # Use BytesIO pattern to load PIL image
        input_image_pil = PIL.Image.open(io.BytesIO(input_image_artifact.value))
        input_image_pil = input_image_pil.convert("RGB")

        # Get parameters
        confidence_threshold = float(self.get_parameter_value("confidence_threshold") or 0.5)
        dilation = float(self.get_parameter_value("dilation") or 0.0)

        self.append_value_to_parameter(
            "logs", f"Running face detection (confidence threshold: {confidence_threshold})...\n"
        )

        # Run YOLO inference
        results = model(input_image_pil)

        # Parse results using supervision
        detections = Detections.from_ultralytics(results[0])

        # Get image dimensions for boundary clamping
        img_width, img_height = input_image_pil.size

        # Filter by confidence threshold and convert to output format
        detected_faces = []
        for i in range(len(detections)):
            confidence = float(detections.confidence[i])
            if confidence >= confidence_threshold:
                # Get bounding box coordinates (x1, y1, x2, y2)
                x1, y1, x2, y2 = detections.xyxy[i]

                # Convert to x, y, width, height format
                bbox = BoundingBox(x=int(x1), y=int(y1), width=int(x2 - x1), height=int(y2 - y1))

                # Apply dilation if specified
                if dilation > 0:
                    bbox = self._dilate_bbox(bbox, dilation, img_width, img_height)

                detected_faces.append(
                    {
                        "x": bbox.x,
                        "y": bbox.y,
                        "width": bbox.width,
                        "height": bbox.height,
                        "confidence": float(confidence),
                    }
                )

        self.append_value_to_parameter("logs", f"Detected {len(detected_faces)} face(s)\n")

        # Set output
        self.set_parameter_value("detected_faces", detected_faces)
        self.parameter_output_values["detected_faces"] = detected_faces
