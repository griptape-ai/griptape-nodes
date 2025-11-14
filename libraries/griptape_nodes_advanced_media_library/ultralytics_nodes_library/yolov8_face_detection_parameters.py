import contextlib
import logging
from collections.abc import Iterator

import huggingface_hub
from diffusers_nodes_library.common.utils.huggingface_utils import model_cache  # type: ignore[reportMissingImports]
from diffusers_nodes_library.common.utils.logging_utils import StdoutCapture  # type: ignore[reportMissingImports]
from ultralytics import YOLO  # type: ignore[reportMissingImports]

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode
from griptape_nodes.exe_types.param_components.huggingface.huggingface_repo_parameter import HuggingFaceRepoParameter
from griptape_nodes.traits.slider import Slider

logger = logging.getLogger("ultralytics_nodes_library")


class YOLOv8FaceDetectionParameters:
    def __init__(self, node: BaseNode):
        self._node = node
        self._huggingface_repo_parameter = HuggingFaceRepoParameter(
            node,
            repo_ids=[
                "arnabdhar/YOLOv8-Face-Detection",
            ],
        )

    def add_input_parameters(self) -> None:
        self._huggingface_repo_parameter.add_input_parameters()
        
        # Add confidence threshold parameter
        self._node.add_parameter(
            Parameter(
                name="confidence_threshold",
                input_types=["float"],
                type="float",
                tooltip="Minimum confidence threshold for face detection (0.0-1.0)",
                default_value=0.5,
                traits={Slider(min_val=0.0, max_val=1.0)},
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        
        # Add dilation parameter
        self._node.add_parameter(
            Parameter(
                name="dilation",
                input_types=["float"],
                type="float",
                tooltip="Expand bounding boxes by percentage (0 = no expansion, 10 = 10% larger)",
                default_value=0.0,
                traits={Slider(min_val=0.0, max_val=100.0)},
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )

    def add_logs_output_parameter(self) -> None:
        self._node.add_parameter(
            Parameter(
                name="logs",
                output_type="str",
                allowed_modes={ParameterMode.OUTPUT},
                tooltip="logs",
                ui_options={"multiline": True},
            )
        )

    def get_repo_revision(self) -> tuple[str, str]:
        return self._huggingface_repo_parameter.get_repo_revision()

    def load_model(self) -> YOLO:
        repo_id, revision = self.get_repo_revision()

        # Create a cache key for this specific model
        cache_key = f"yolov8_face_{repo_id}_{revision}"

        # Try to get from cache first
        cached_model = model_cache.get_pipeline(cache_key)
        if cached_model is not None:
            logger.info("Using cached YOLOv8 model: %s", cache_key)
            return cached_model

        # Download the model.pt file from HuggingFace
        model_path = huggingface_hub.hf_hub_download(
            repo_id=repo_id,
            revision=revision,
            filename="model.pt",
            local_files_only=True,
        )

        # Load YOLO model
        logger.info("Loading YOLOv8 model from: %s", model_path)
        model = YOLO(model_path)

        # Cache the model
        model_cache._pipeline_cache[cache_key] = model
        logger.info("Cached YOLOv8 model: %s", cache_key)

        return model

    def validate_before_node_run(self) -> list[Exception] | None:
        return self._huggingface_repo_parameter.validate_before_node_run()

    @contextlib.contextmanager
    def append_stdout_to_logs(self) -> Iterator[None]:
        def callback(data: str) -> None:
            self._node.append_value_to_parameter("logs", data)

        with StdoutCapture(callback):
            yield

