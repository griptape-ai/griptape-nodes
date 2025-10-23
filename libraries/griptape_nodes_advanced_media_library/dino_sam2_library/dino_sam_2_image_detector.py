import logging

import numpy as np
import PIL.Image  # type: ignore[reportMissingImports]
import PIL.ImageDraw  # type: ignore[reportMissingImports]
import torch  # type: ignore[reportMissingImports]
import transformers  # type: ignore[reportMissingImports]
from diffusers_nodes_library.common.utils.huggingface_utils import model_cache  # type: ignore[reportMissingImports]
from diffusers_nodes_library.common.utils.torch_utils import get_best_device
from griptape.artifacts import ImageUrlArtifact
from huggingface_hub import hf_hub_download  # pyright: ignore[reportMissingImports]
from PIL.Image import Image  # type: ignore[reportMissingImports]
from pillow_nodes_library.utils import (  # type: ignore[reportMissingImports]
    image_artifact_to_pil,  # type: ignore[reportMissingImports]
    pil_to_image_artifact,  # type: ignore[reportMissingImports]
)
from sam2.build_sam import HF_MODEL_ID_TO_FILENAMES, build_sam2  # type: ignore[reportMissingImports]
from sam2.sam2_image_predictor import SAM2ImagePredictor  # type: ignore[reportMissingImports]
from utils.image_utils import load_image_from_url_artifact

from dino_sam2_library.dino_sam_2_detector_parameters import DinoSam2DetectorParameters
from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import AsyncResult, ControlNode
from griptape_nodes.exe_types.param_components.log_parameter import LogParameter

logger = logging.getLogger("sam2_nodes_library")


class DinoSam2ImageDetector(ControlNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.params = DinoSam2DetectorParameters(self)
        self.log_params = LogParameter(self)
        self.params.add_input_parameters()
        self.add_parameter(
            Parameter(
                name="input_image",
                input_types=["ImageArtifact", "ImageUrlArtifact"],
                type="ImageArtifact",
                tooltip="Input image for segmentation",
            )
        )
        self.add_parameter(
            Parameter(
                name="prompt",
                input_types=["str"],
                type="str",
                default_value="",
                tooltip="Text prompt for segmentation. Separate objects with periods.",
            )
        )
        self.add_parameter(
            Parameter(
                name="box_threshold",
                input_types=["float"],
                type="float",
                default_value=0.3,
                tooltip="Box threshold for segmentation",
                ui_options={"slider": {"min_val": 0.01, "max_val": 1.0}, "step": 0.01},
            )
        )
        self.add_parameter(
            Parameter(
                name="text_threshold",
                input_types=["float"],
                type="float",
                default_value=0.25,
                tooltip="Text threshold for segmentation",
                ui_options={"slider": {"min_val": 0.01, "max_val": 1.0}, "step": 0.01},
            )
        )
        self.add_parameter(
            Parameter(
                name="mask_threshold",
                input_types=["float"],
                type="float",
                default_value=0.0,
                tooltip="The threshold to use when converting mask logits to binary masks. ",
                ui_options={"slider": {"min_val": 0.0, "max_val": 1.0}, "step": 0.01},
            )
        )
        self.add_parameter(
            Parameter(
                name="output_mask",
                output_type="ImageArtifact",
                tooltip="The segmentation mask as an image",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        self.log_params.add_output_parameters()

    def get_input_image_pil(self) -> Image:
        """Get the input image as a PIL Image."""
        input_image_artifact = self.get_parameter_value("input_image")

        if isinstance(input_image_artifact, ImageUrlArtifact):
            input_image_artifact = load_image_from_url_artifact(input_image_artifact)

        image_pil = image_artifact_to_pil(input_image_artifact)
        if image_pil.mode == "RGBA":
            # Composite the RGBA image over the black background using the alpha channel
            black_background = PIL.Image.new("RGBA", image_pil.size, (0, 0, 0, 255))
            image_pil = PIL.Image.alpha_composite(black_background, image_pil)
        image_pil = image_pil.convert("RGB")
        return image_pil

    def get_prompt(self) -> str:
        """Get the text prompt for segmentation."""
        # DINO prompt must be lower case.
        return self.get_parameter_value("prompt").lower()

    def get_box_threshold(self) -> float:
        """Get the box threshold for segmentation."""
        return float(self.get_parameter_value("box_threshold"))

    def get_text_threshold(self) -> float:
        """Get the text threshold for segmentation."""
        return float(self.get_parameter_value("text_threshold"))

    def get_mask_threshold(self) -> float:
        """Get the mask threshold for segmentation."""
        return float(self.get_parameter_value("mask_threshold"))

    def process(self) -> AsyncResult | None:
        yield lambda: self._process()

    def _process(self) -> AsyncResult | None:
        self.log_params.append_to_logs("Preparing models...\n")

        # -------------------------------------------------------------
        # Model loading
        # -------------------------------------------------------------
        with (
            self.log_params.append_profile_to_logs("Loading models"),
            self.log_params.append_logs_to_logs(logger=logger),
        ):
            dino_repo_id, dino_revision = self.params.get_dino_repo_revision()
            dino_processor = model_cache.from_pretrained(
                transformers.AutoProcessor,
                pretrained_model_name_or_path=dino_repo_id,
                revision=dino_revision,
                local_files_only=True,
            )
            dino_model = model_cache.from_pretrained(
                transformers.AutoModelForZeroShotObjectDetection,
                pretrained_model_name_or_path=dino_repo_id,
                revision=dino_revision,
                local_files_only=True,
            )

            sam2_repo_id, sam2_revision = self.params.get_sam2_repo_revision()
            sam2_config_name, sam2_checkpoint_name = HF_MODEL_ID_TO_FILENAMES[sam2_repo_id]
            sam2_ckpt_path = hf_hub_download(
                repo_id=sam2_repo_id,
                filename=sam2_checkpoint_name,
                revision=sam2_revision,
                local_files_only=True,
            )
            sam2_model = build_sam2(config_file=sam2_config_name, ckpt_path=sam2_ckpt_path, device="cpu")
            sam2_predictor = SAM2ImagePredictor(
                sam_model=sam2_model,
                mask_threshold=self.get_mask_threshold(),
            )

            device = get_best_device()
            dino_model.to(device)
            sam2_model.to(device)

        # -------------------------------------------------------------
        # Inference
        # -------------------------------------------------------------
        self.log_params.append_to_logs("Starting segmentation...\n")

        with (
            self.log_params.append_profile_to_logs("Processing image segmentation"),
            self.log_params.append_logs_to_logs(logger=logger),
            self.log_params.append_stdout_to_logs(),
        ):
            input_image_pil = self.get_input_image_pil()
            dino_inputs = dino_processor(
                images=input_image_pil,
                text=self.get_prompt(),
                return_tensors="pt",
            )
            # dino_inputs is expected to have the following keys:
            #  - input_ids: tensor of shape (batch_size, sequence_length)
            #  - token_type_ids: tensor of shape (batch_size, sequence_length)
            #  - attention_mask: tensor of shape (batch_size, sequence_length)
            #  - pixel_values: tensor of shape (batch_size, num_channels, height, width)
            #  - pixel_mask: tensor of shape (batch_size, height, width)

            dino_inputs.to(device=dino_model.device)
            with torch.no_grad():
                outputs = dino_model(**dino_inputs)

            dino_results: list[dict] = dino_processor.post_process_grounded_object_detection(
                outputs,
                dino_inputs.input_ids,
                threshold=self.get_box_threshold(),
                text_threshold=self.get_text_threshold(),
                target_sizes=[k.size[::-1] for k in [input_image_pil]],
            )
            # dino_results is expected to be a list of dictionaries with the following keys:
            #  - boxes: tensor of shape (num_boxes, 4) with bounding box coordinates
            #  - scores: tensor of shape (num_boxes,) with confidence scores
            #  - text_labels: list of strings with the labels for each box
            #  - labels: list of strings with the labels for each box (same as text_labels)

            # Move tensors in dino_results to the same device as dino_model
            for key, value in dino_results[0].items():
                if isinstance(value, torch.Tensor):
                    dino_results[0][key] = value.to(device=dino_model.device)

            masks_to_merge = []
            boxes = [box for dino_result in dino_results for box in dino_result["boxes"]]
            for box_tensor in boxes:
                box = box_tensor.cpu().numpy().tolist()
                input_image_pil = self.get_input_image_pil()
                image_np = np.array(input_image_pil)
                sam2_predictor.set_image(image_np)
                masks, _scores, _logits = sam2_predictor.predict(
                    box=box,
                    multimask_output=False,
                )
                masks_to_merge.append(masks[0])  # Append the first mask for the first box

            # Merge all masks into a single mask
            mask = np.zeros((input_image_pil.height, input_image_pil.width), dtype=np.uint8)
            for m in masks_to_merge:
                mask = np.maximum(mask, m)

            # Convert mask to pil image
            mask = (mask * 255).astype(np.uint8)  # Ensure mask is in uint8 format
            output_mask_pil = PIL.Image.fromarray(mask, mode="L")  # Convert to binary mask (0-255)

        # -------------------------------------------------------------
        # Process output & publish
        # -------------------------------------------------------------
        with (
            self.log_params.append_profile_to_logs("Processing output mask"),
            self.log_params.append_logs_to_logs(logger=logger),
        ):
            output_mask_artifact = pil_to_image_artifact(output_mask_pil)
            self.set_parameter_value("output_mask", output_mask_artifact)
            self.parameter_output_values["output_mask"] = output_mask_artifact
