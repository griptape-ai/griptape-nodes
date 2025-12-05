import copy
import logging

import cv2  # type: ignore[reportMissingImports]
import huggingface_hub  # pyright: ignore[reportMissingImports]
import numpy as np
import PIL.Image  # type: ignore[reportMissingImports]
from griptape.artifacts import ImageUrlArtifact
from PIL.Image import Image  # type: ignore[reportMissingImports]
from pillow_nodes_library.utils import (  # type: ignore[reportMissingImports]
    image_artifact_to_pil,  # type: ignore[reportMissingImports]
    pil_to_image_artifact,  # type: ignore[reportMissingImports]
)
from safetensors.torch import load_file  # type: ignore[reportMissingImports]
from utils.image_utils import load_image_from_url_artifact  # type: ignore[reportMissingImports]

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import AsyncResult, ControlNode
from griptape_nodes.exe_types.param_components.huggingface.huggingface_repo_file_parameter import (
    HuggingFaceRepoFileParameter,  # type: ignore[reportMissingImports]
)
from griptape_nodes.exe_types.param_components.log_parameter import LogParameter
from openpose_nodes_library.model import util  # type: ignore[reportMissingImports]
from openpose_nodes_library.model.body import Body  # type: ignore[reportMissingImports]
from openpose_nodes_library.model.hand import Hand  # type: ignore[reportMissingImports]

logger = logging.getLogger("openpose")


def calculate_processing_size(original_height: int, original_width: int, max_dim: int | None) -> tuple[int, int, float]:
    """Calculate processing dimensions based on max_dim constraint."""
    if max_dim is None:
        return original_height, original_width, 1.0

    # Find the longer dimension
    longer_dim = max(original_height, original_width)

    # If already smaller than max_dim, don't scale
    if longer_dim <= max_dim:
        return original_height, original_width, 1.0

    # Calculate scale factor to make longest dimension = max_dim
    scale_factor = max_dim / longer_dim
    new_height = int(original_height * scale_factor)
    new_width = int(original_width * scale_factor)

    return new_height, new_width, scale_factor


def scale_keypoints_back(keypoints: np.ndarray | None, scale_factor: float) -> np.ndarray | None:
    """Scale keypoints back to original resolution."""
    if keypoints is None or len(keypoints) == 0 or scale_factor == 1.0:
        return keypoints

    scaled = keypoints.copy()
    scaled[:, 0] = keypoints[:, 0] / scale_factor  # x coordinates
    scaled[:, 1] = keypoints[:, 1] / scale_factor  # y coordinates
    return scaled


def scale_pose_results_back(
    candidate: np.ndarray | None, subset: np.ndarray | None, scale_factor: float
) -> tuple[np.ndarray | None, np.ndarray | None]:
    """Scale body pose results back to original resolution."""
    if scale_factor == 1.0:
        return candidate, subset

    if candidate is not None and len(candidate) > 0:
        scaled_candidate = candidate.copy()
        scaled_candidate[:, 0] = candidate[:, 0] / scale_factor  # x coordinates
        scaled_candidate[:, 1] = candidate[:, 1] / scale_factor  # y coordinates
        return scaled_candidate, subset

    return candidate, subset


class OpenPoseImageDetection(ControlNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._huggingface_repo_parameter = HuggingFaceRepoFileParameter(
            self,
            repo_files=[
                ("dylanholmes/openpose-safetensors", "body25.safetensors"),
                ("dylanholmes/openpose-safetensors", "coco.safetensors"),
            ],
        )
        self.log_params = LogParameter(self)

        self._huggingface_repo_parameter.add_input_parameters()
        self.add_parameter(
            Parameter(
                name="input_image",
                input_types=["ImageArtifact", "ImageUrlArtifact"],
                type="ImageArtifact",
                tooltip="Input image for pose detection",
            )
        )
        self.add_parameter(
            Parameter(
                name="max_dim",
                input_types=["int"],
                type="int",
                tooltip="Maximum dimension for processing (preserves aspect ratio)",
                default_value=256,
            )
        )
        self.add_parameter(
            Parameter(
                name="black_background",
                input_types=["bool"],
                type="bool",
                tooltip="Draw poses on black background instead of original image",
                default_value=False,
            )
        )
        self.add_parameter(
            Parameter(
                name="output_image",
                output_type="ImageUrlArtifact",
                tooltip="Image with pose detection results",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        self.log_params.add_output_parameters()

        # Internal state
        self._model = None
        self._repo_id = None
        self._revision = None
        self._model_file = None

    def validate_before_node_run(self) -> list[Exception] | None:
        errors = self._huggingface_repo_parameter.validate_before_node_run()

        if not self.get_parameter_value("input_image"):
            if errors is None:
                errors = []
            errors.append(Exception("No input image provided"))

        return errors or None

    def get_input_image(self) -> Image:
        input_image_artifact = self.get_parameter_value("input_image")
        if input_image_artifact is None:
            logger.exception("No input image specified")

        if isinstance(input_image_artifact, ImageUrlArtifact):
            input_image_artifact = load_image_from_url_artifact(input_image_artifact)
        input_image_pil = image_artifact_to_pil(input_image_artifact)
        input_image_pil = input_image_pil.convert("RGB")
        return input_image_pil

    def publish_preview_placeholder_image(self, input_image_pil: Image) -> None:
        preview_placeholder_image_pil = PIL.Image.new("RGB", input_image_pil.size, color="black")
        preview_placeholder_image_url_artifact = pil_to_image_artifact(preview_placeholder_image_pil)
        self.publish_update_to_parameter("output_image", preview_placeholder_image_url_artifact)

    def publish_output_image(self, output_image: Image) -> None:
        output_image_url_artifact = pil_to_image_artifact(output_image)
        self.set_parameter_value("output_image", output_image_url_artifact)
        self.parameter_output_values["output_image"] = output_image_url_artifact

    def get_openpose_model(self) -> tuple[Body | Hand, str]:
        repo_id, revision = self._huggingface_repo_parameter.get_repo_revision()
        model_file = self._huggingface_repo_parameter.get_repo_filename()

        # Download the model file from HuggingFace
        model_path = huggingface_hub.hf_hub_download(
            repo_id=repo_id,
            revision=revision,
            filename=model_file,
            local_files_only=True,
        )

        # Extract model type from filename
        if "body25" in model_file:
            model_type = "body25"
        elif "coco" in model_file:
            model_type = "coco"
        elif "face" in model_file:
            model_type = "face"
        elif "hand" in model_file:
            model_type = "hand"
        else:
            model_type = "body25"  # Default fallback

        # Load model using safetensors
        state_dict = load_file(model_path)

        if model_type == "hand":
            self._model = Hand(state_dict)
        else:
            self._model = Body(state_dict, model_type)

        self._model_type = model_type
        self._repo_id = repo_id
        self._revision = revision
        self._model_file = model_file

        return self._model, model_type

    def process(self) -> AsyncResult | None:
        yield lambda: self._process()

    def _process(self) -> AsyncResult | None:
        self.log_params.clear_logs()
        self.log_params.append_to_logs("Starting OpenPose image detection...\n")

        input_image_pil = self.get_input_image()
        max_dim = self.get_parameter_value("max_dim")
        black_background = self.get_parameter_value("black_background") or False

        # Immediately set a preview placeholder image
        self.publish_preview_placeholder_image(input_image_pil)

        # Get OpenPose model
        with self.log_params.append_profile_to_logs("Loading OpenPose model"):
            openpose_model, model_type = self.get_openpose_model()
            self.log_params.append_to_logs(f"Loaded {model_type} model\n")

        # Convert PIL to numpy (OpenCV format: BGR)
        input_image_bgr = np.array(input_image_pil.convert("RGB"))[:, :, ::-1]  # RGB to BGR

        # Calculate processing dimensions
        original_height, original_width = input_image_bgr.shape[:2]
        proc_height, proc_width, scale_factor = calculate_processing_size(original_height, original_width, max_dim)

        self.log_params.append_to_logs(f"Image size: {original_width}x{original_height}\n")
        if scale_factor != 1.0:
            self.log_params.append_to_logs(f"Processing at: {proc_width}x{proc_height} (scale: {scale_factor:.2f})\n")

        # Resize image for processing if needed
        if scale_factor != 1.0:
            processing_img = cv2.resize(input_image_bgr, (proc_width, proc_height), interpolation=cv2.INTER_LINEAR)
        else:
            processing_img = input_image_bgr

        # Create canvas - either original image or black background
        if black_background:
            canvas = np.zeros_like(input_image_bgr)  # Black background
        else:
            canvas = copy.deepcopy(input_image_bgr)  # Original image

        # Run pose detection based on model type
        with self.log_params.append_profile_to_logs(f"Running {model_type} pose detection"):
            if model_type == "hand":
                # Hand-only detection
                peaks = openpose_model(processing_img)
                # Ensure peaks is an ndarray
                if isinstance(peaks, tuple):
                    peaks = np.array(peaks) if peaks else None
                # Scale keypoints back to original resolution
                scaled_peaks = scale_keypoints_back(peaks, scale_factor)

                # Draw hand keypoints on original resolution canvas
                canvas = util.draw_handpose(canvas, [scaled_peaks])
                self.log_params.append_to_logs("Hand pose detection completed\n")
            else:
                # Body pose detection
                candidate, subset = openpose_model(processing_img)
                # Scale results back to original resolution
                scaled_candidate, scaled_subset = scale_pose_results_back(candidate, subset, scale_factor)
                if scaled_candidate is not None and scaled_subset is not None:
                    canvas = util.draw_bodypose(canvas, scaled_candidate, scaled_subset, model_type)
                self.log_params.append_to_logs("Body pose detection completed\n")

        # Convert back to RGB and then PIL
        output_rgb = canvas[:, :, ::-1]  # BGR to RGB
        output_pil = PIL.Image.fromarray(output_rgb)
        self.publish_output_image(output_pil)

        self.log_params.append_to_logs("Image detection process completed successfully!\n")
