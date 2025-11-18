import contextlib
import logging
from collections.abc import Callable, Iterator

import huggingface_hub
from diffusers_nodes_library.common.utils.logging_utils import StdoutCapture  # type: ignore[import-untyped]
from ultralytics import YOLO  # type: ignore[import-untyped]

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

    def get_cache_key(self) -> str:
        """Generate cache key for the current model configuration."""
        repo_id, revision = self.get_repo_revision()
        return f"yolov8_face_{repo_id}_{revision}"

    def get_model_builder(self) -> Callable[[], YOLO]:
        """Return a builder function that loads the YOLO model."""
        repo_id, revision = self.get_repo_revision()

        def builder() -> YOLO:
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

            return model

        return builder

    def validate_before_node_run(self) -> list[Exception] | None:
        return self._huggingface_repo_parameter.validate_before_node_run()

    @contextlib.contextmanager
    def append_stdout_to_logs(self) -> Iterator[None]:
        def callback(data: str) -> None:
            self._node.append_value_to_parameter("logs", data)

        with StdoutCapture(callback):
            yield
