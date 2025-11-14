import io
import logging

import PIL.Image
from griptape.artifacts import ImageUrlArtifact
from supervision import Detections  # type: ignore[reportMissingImports]
from utils.image_utils import load_image_from_url_artifact  # type: ignore[reportMissingImports]

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import AsyncResult, ControlNode
from ultralytics_nodes_library.yolov8_face_detection_parameters import (  # type: ignore[reportMissingImports]
    YOLOv8FaceDetectionParameters,
)

logger = logging.getLogger("ultralytics_nodes_library")


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

    def validate_before_node_run(self) -> list[Exception] | None:
        errors = self.params.validate_before_node_run()

        if not self.get_parameter_value("input_image"):
            if errors is None:
                errors = []
            errors.append(Exception("No input image provided"))

        return errors or None

    def process(self) -> AsyncResult | None:
        yield lambda: self._process()

    def _process(self) -> AsyncResult | None:
        input_image_artifact = self.get_parameter_value("input_image")

        # Convert ImageUrlArtifact to ImageArtifact if needed
        if isinstance(input_image_artifact, ImageUrlArtifact):
            input_image_artifact = load_image_from_url_artifact(input_image_artifact)
        
        # Use BytesIO pattern to load PIL image
        input_image_pil = PIL.Image.open(io.BytesIO(input_image_artifact.value))
        input_image_pil = input_image_pil.convert("RGB")

        self.append_value_to_parameter("logs", "Loading YOLOv8 face detection model...\n")
        with self.params.append_stdout_to_logs():
            model = self.params.load_model()

        # Get confidence threshold
        confidence_threshold = float(self.get_parameter_value("confidence_threshold") or 0.5)
        
        self.append_value_to_parameter("logs", f"Running face detection (confidence threshold: {confidence_threshold})...\n")
        
        # Run YOLO inference
        results = model(input_image_pil)
        
        # Parse results using supervision
        detections = Detections.from_ultralytics(results[0])
        
        # Filter by confidence threshold and convert to output format
        detected_faces = []
        for i in range(len(detections)):
            confidence = float(detections.confidence[i])
            if confidence >= confidence_threshold:
                # Get bounding box coordinates (x1, y1, x2, y2)
                x1, y1, x2, y2 = detections.xyxy[i]
                
                # Convert to x, y, width, height format
                x = int(x1)
                y = int(y1)
                width = int(x2 - x1)
                height = int(y2 - y1)
                
                detected_faces.append({
                    "x": x,
                    "y": y,
                    "width": width,
                    "height": height,
                    "confidence": float(confidence),
                })
        
        self.append_value_to_parameter("logs", f"Detected {len(detected_faces)} face(s)\n")
        
        # Set output
        self.set_parameter_value("detected_faces", detected_faces)
        self.parameter_output_values["detected_faces"] = detected_faces

