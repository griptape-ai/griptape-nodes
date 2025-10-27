import logging
import tempfile
from pathlib import Path

import diffusers  # type: ignore[reportMissingImports]
import imageio  # type: ignore[reportMissingImports]
import numpy as np
import PIL.Image  # type: ignore[reportMissingImports]
import requests
import torch  # type: ignore[reportMissingImports]
import transformers  # type: ignore[reportMissingImports]
from diffusers_nodes_library.common.utils.huggingface_utils import model_cache  # type: ignore[reportMissingImports]
from diffusers_nodes_library.common.utils.torch_utils import get_best_device  # type: ignore[reportMissingImports]
from griptape.artifacts.video_url_artifact import VideoUrlArtifact
from huggingface_hub import hf_hub_download  # pyright: ignore[reportMissingImports]
from sam2.build_sam import HF_MODEL_ID_TO_FILENAMES, build_sam2_video_predictor  # type: ignore[reportMissingImports]

from dino_sam2_library.dino_sam_2_detector_parameters import DinoSam2DetectorParameters
from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import AsyncResult, ControlNode
from griptape_nodes.exe_types.param_components.log_parameter import LogParameter
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

logger = logging.getLogger("sam2_nodes_library")


class DinoSam2VideoDetector(ControlNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.params = DinoSam2DetectorParameters(self)
        self.log_params = LogParameter(self)

        self.params.add_input_parameters()

        self.add_parameter(
            Parameter(
                name="input_video",
                input_types=["VideoArtifact", "VideoUrlArtifact"],
                type="VideoUrlArtifact",
                tooltip="Input video for segmentation",
            )
        )

        self.add_parameter(
            Parameter(
                name="prompt",
                input_types=["str"],
                type="str",
                default_value="",
                tooltip="Text prompt for object detection. Separate objects with periods.",
            )
        )

        self.add_parameter(
            Parameter(
                name="prompt_frame_idx",
                input_types=["int"],
                type="int",
                default_value=0,
                tooltip="Frame index to add prompts on (0-based)",
                ui_options={"min": 0},
            )
        )

        self.add_parameter(
            Parameter(
                name="box_threshold",
                input_types=["float"],
                type="float",
                default_value=0.3,
                tooltip="Box threshold for object detection",
                ui_options={"slider": {"min_val": 0.01, "max_val": 1.0}, "step": 0.01},
            )
        )

        self.add_parameter(
            Parameter(
                name="text_threshold",
                input_types=["float"],
                type="float",
                default_value=0.25,
                tooltip="Text threshold for object detection",
                ui_options={"slider": {"min_val": 0.01, "max_val": 1.0}, "step": 0.01},
            )
        )

        self.add_parameter(
            Parameter(
                name="output_video",
                output_type="VideoUrlArtifact",
                tooltip="The segmentation masks as video",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

        self.log_params.add_output_parameters()

    def get_video_mp4(self) -> str:
        """Get the input video as a URL."""
        url = self.get_parameter_value("input_video").value
        return url

    def get_video_frames_pil(self) -> list[PIL.Image.Image]:
        """Get the input video frames as a list of PIL Image objects."""
        return diffusers.utils.load_video(self.get_video_mp4())

    def get_prompt(self) -> str:
        """Get the prompt text for object detection."""
        # DINO prompt must be lower case.
        return self.get_parameter_value("prompt").lower()

    def get_prompt_frame_idx(self) -> int:
        """Get the frame index to add prompts on."""
        return int(self.get_parameter_value("prompt_frame_idx"))

    def get_box_threshold(self) -> float:
        """Get the box threshold for object detection."""
        return float(self.get_parameter_value("box_threshold"))

    def get_text_threshold(self) -> float:
        """Get the text threshold for object detection."""
        return float(self.get_parameter_value("text_threshold"))

    def process(self) -> AsyncResult | None:
        yield lambda: self._process()

    def _process(self) -> AsyncResult | None:  # noqa: PLR0915, C901, PLR0912
        self.log_params.append_to_logs("Preparing models...\n")

        # -------------------------------------------------------------
        # Model loading
        # -------------------------------------------------------------
        with (
            self.log_params.append_profile_to_logs("Loading models"),
            self.log_params.append_logs_to_logs(logger=logger),
        ):
            # Load DINO model for object detection
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

            # Load SAM2 model for video segmentation
            sam2_repo_id, sam2_revision = self.params.get_sam2_repo_revision()
            sam2_config_name, sam2_checkpoint_name = HF_MODEL_ID_TO_FILENAMES[sam2_repo_id]
            sam2_ckpt_path = hf_hub_download(
                repo_id=sam2_repo_id,
                filename=sam2_checkpoint_name,
                revision=sam2_revision,
                local_files_only=True,
            )

            device = get_best_device()
            sam2_predictor = build_sam2_video_predictor(
                config_file=sam2_config_name, ckpt_path=sam2_ckpt_path, device=device
            )
            dino_model.to(device)

        # -------------------------------------------------------------
        # Video processing
        # -------------------------------------------------------------
        self.log_params.append_to_logs("Loading video frames...\n")

        with (
            self.log_params.append_profile_to_logs("Loading video frames"),
            self.log_params.append_logs_to_logs(logger=logger),
        ):
            # Load video frames
            frames = self.get_video_frames_pil()
            self.log_params.append_to_logs(f"Loaded {len(frames)} frames\n")

            # Convert PIL frames to numpy arrays for SAM2
            [np.array(frame) for frame in frames]

        # -------------------------------------------------------------
        # DINO Object Detection on Prompt Frame
        # -------------------------------------------------------------
        self.log_params.append_to_logs("Running DINO object detection...\n")

        with (
            self.log_params.append_profile_to_logs("Processing DINO object detection"),
            self.log_params.append_logs_to_logs(logger=logger),
            self.log_params.append_stdout_to_logs(),
        ):
            # Use the specified prompt frame for object detection
            prompt_frame = frames[self.get_prompt_frame_idx()]

            # Process with DINO
            inputs = dino_processor(
                images=prompt_frame,
                text=self.get_prompt(),
                return_tensors="pt",
            )
            inputs.to(device=dino_model.device)

            with torch.no_grad():
                outputs = dino_model(**inputs)

            dino_results = dino_processor.post_process_grounded_object_detection(
                outputs,
                inputs.input_ids,
                threshold=self.get_box_threshold(),
                text_threshold=self.get_text_threshold(),
                target_sizes=[prompt_frame.size[::-1]],
            )

            boxes = (
                dino_results[0]["boxes"].cpu().numpy()
                if len(dino_results) > 0 and len(dino_results[0]["boxes"]) > 0
                else []
            )
            self.log_params.append_to_logs(f"DINO detected {len(boxes)} objects\n")

        # -------------------------------------------------------------
        # SAM2 Video Segmentation
        # -------------------------------------------------------------
        self.log_params.append_to_logs("Starting SAM2 video segmentation...\n")

        with tempfile.TemporaryDirectory() as tmp_dir:
            video_path = Path(tmp_dir) / "input_video.mp4"

            # 1. Download the video
            video_data = requests.get(self.get_video_mp4(), timeout=30).content
            with Path(video_path).open("wb") as f:
                f.write(video_data)

            # 2. Create output folder for frames
            frame_dir = Path(tmp_dir) / "frames"
            Path(frame_dir).mkdir(parents=True, exist_ok=True)

            # 3. Read video and save frames
            with imageio.get_reader(video_path) as reader:
                meta = reader.get_meta_data()
                fps = int(meta.get("fps"))
                for i, frame in enumerate(reader):
                    img = PIL.Image.fromarray(frame)
                    img.save(Path(frame_dir) / f"{i:05d}.jpg", format="JPEG")

            with (
                self.log_params.append_profile_to_logs("Processing SAM2 video segmentation"),
                self.log_params.append_logs_to_logs(logger=logger),
                self.log_params.append_stdout_to_logs(),
            ):
                # Initialize SAM2 video state
                inference_state = sam2_predictor.init_state(video_path=str(frame_dir))

                # Add bounding boxes as prompts to SAM2
                video_segments = {}
                if len(boxes) > 0:
                    for obj_id, box in enumerate(boxes, 1):
                        # Add box prompt to the specified frame
                        sam2_predictor.add_new_points_or_box(
                            inference_state=inference_state,
                            frame_idx=self.get_prompt_frame_idx(),
                            obj_id=obj_id,
                            box=box,
                        )

                    # Propagate masks through video
                    for out_frame_idx, out_obj_ids, out_mask_logits in sam2_predictor.propagate_in_video(
                        inference_state
                    ):
                        video_segments[out_frame_idx] = {
                            out_obj_id: (out_mask_logits[i] > 0.0).cpu().numpy()
                            for i, out_obj_id in enumerate(out_obj_ids)
                        }
                else:
                    self.log_params.append_to_logs("No objects detected, creating empty segmentation\n")
                    # Create empty masks for all frames
                    for frame_idx in range(len(frames)):
                        video_segments[frame_idx] = {}

            # -------------------------------------------------------------
            # Export video & publish
            # -------------------------------------------------------------
            with (
                self.log_params.append_profile_to_logs("Exporting segmentation video"),
                self.log_params.append_logs_to_logs(logger=logger),
                self.log_params.append_stdout_to_logs(),
            ):
                # Convert masks to video frames
                mask_frames = []
                for frame_idx in range(len(frames)):
                    if frame_idx in video_segments:
                        # Combine all object masks for this frame
                        combined_mask = np.zeros(frames[frame_idx].size[::-1], dtype=np.uint8)
                        for mask_tensor in video_segments[frame_idx].values():
                            if mask_tensor is not None:
                                mask = (mask_tensor * 255).astype(np.uint8).squeeze()
                                combined_mask = np.maximum(combined_mask, mask)
                        mask_frame = PIL.Image.fromarray(combined_mask, mode="L").convert("RGB")
                    else:
                        # No mask for this frame, create black frame
                        mask_frame = PIL.Image.new("RGB", frames[frame_idx].size, (0, 0, 0))

                    mask_frames.append(mask_frame)

                # Export to video file
                with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as temp_file_obj:
                    temp_file = Path(temp_file_obj.name)

                try:
                    diffusers.utils.export_to_video(mask_frames, str(temp_file), fps=fps)
                    self._publish_output_video(temp_file)
                    self.log_params.append_to_logs(f"Generated video with {len(mask_frames)} mask frames\n")
                finally:
                    if temp_file.exists():
                        temp_file.unlink()

    def _publish_output_video(self, video_path: Path) -> None:
        """Publish the output video."""
        import uuid

        filename = f"{uuid.uuid4()}{video_path.suffix}"
        url = GriptapeNodes.StaticFilesManager().save_static_file(video_path.read_bytes(), filename)
        self.parameter_output_values["output_video"] = VideoUrlArtifact(url)
