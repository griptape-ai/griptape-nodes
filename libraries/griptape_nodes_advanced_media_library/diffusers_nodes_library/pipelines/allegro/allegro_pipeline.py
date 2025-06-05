import logging
from typing import Any, List

import diffusers  # type: ignore[reportMissingImports]
from diffusers.utils import export_to_video  # type: ignore[reportMissingImports]
import PIL.Image

from diffusers_nodes_library.common.parameters.log_parameter import (
    LogParameter,  # type: ignore[reportMissingImports]
)
from diffusers_nodes_library.common.utils.huggingface_utils import (
    model_cache,  # type: ignore[reportMissingImports]
)
from diffusers_nodes_library.pipelines.allegro.allegro_pipeline_parameters import (
    AllegroPipelineParameters,  # type: ignore[reportMissingImports]
)
from diffusers_nodes_library.pipelines.allegro.optimize_allegro_pipeline_memory_footprint import (
    optimize_allegro_pipeline_memory_footprint,  # type: ignore[reportMissingImports]
    print_allegro_pipeline_memory_footprint,  # type: ignore[reportMissingImports]
)
from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.exe_types.node_types import AsyncResult, ControlNode
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes  # type: ignore[reportMissingImports]
from griptape_nodes_library.video.video_url_artifact import VideoUrlArtifact  # type: ignore[reportMissingImports]
from pillow_nodes_library.utils import pil_to_image_artifact  # type: ignore[reportMissingImports]

logger = logging.getLogger("diffusers_nodes_library")


class AllegroPipeline(ControlNode):
    """Griptape wrapper around diffusers.AllegroPipeline for text-to-video generation."""

    def __init__(self, **kwargs) -> None:  # noqa: D401
        super().__init__(**kwargs)
        self.pipe_params = AllegroPipelineParameters(self)
        self.log_params = LogParameter(self)

        # Register parameters
        self.pipe_params.add_input_parameters()
        self.pipe_params.add_output_parameters()
        self.log_params.add_output_parameters()

    # ------------------------------------------------------------------
    # Lifecycle hooks
    # ------------------------------------------------------------------
    def after_value_set(
        self, parameter: Parameter, value: Any, modified_parameters_set: set[str]
    ) -> None:
        self.pipe_params.after_value_set(parameter, value, modified_parameters_set)

    def validate_before_node_run(self) -> List[Exception] | None:  # noqa: D401
        errors = self.pipe_params.validate_before_node_run()
        return errors or None

    def preprocess(self) -> None:
        self.pipe_params.preprocess()

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------
    def process(self) -> AsyncResult | None:  # noqa: D401
        yield lambda: self._process()

    def _process(self) -> AsyncResult | None:  # noqa: C901
        # ------------------------------------------------------------------
        # Housekeeping
        # ------------------------------------------------------------------
        self.preprocess()
        self.log_params.append_to_logs("Preparing models...\n")

        # ------------------------------------------------------------------
        # Model loading
        # ------------------------------------------------------------------
        with self.log_params.append_profile_to_logs("Loading model metadata"):
            repo_id, revision = self.pipe_params.get_repo_revision()
            pipe: diffusers.AllegroPipeline = model_cache.from_pretrained(
                diffusers.AllegroPipeline,
                pretrained_model_name_or_path=repo_id,
                revision=revision,
                torch_dtype="auto",
                local_files_only=True,
            )

        with (
            self.log_params.append_profile_to_logs("Loading model"),
            self.log_params.append_logs_to_logs(logger),
        ):
            optimize_allegro_pipeline_memory_footprint(pipe)

        # ------------------------------------------------------------------
        # Inference
        # ------------------------------------------------------------------
        num_inference_steps = self.pipe_params.get_num_inference_steps()

        def callback_on_step_end(
            step: int, _timestep: int, _callback_kwargs: dict
        ) -> dict:  # noqa: D401
            if step < num_inference_steps - 1:
                self.log_params.append_to_logs(
                    f"Starting inference step {step + 2} of {num_inference_steps}...\n"
                )
            return {}

        self.log_params.append_to_logs(
            f"Starting inference step 1 of {num_inference_steps}...\n"
        )

        video_output = pipe(
            **self.pipe_params.get_pipe_kwargs(),
            output_type="pil",
            callback_on_step_end=callback_on_step_end,
        ).frames  # type: ignore[attr-defined]

        # `video_output` is expected to be list of list of PIL.Image or np array.
        frames: list[PIL.Image.Image]
        if isinstance(video_output, list):
            frames = video_output[0]  # type: ignore[assignment]
        else:
            # Fallback to first element if numpy array
            frames = [PIL.Image.fromarray(frame) for frame in video_output]

        # Save video to a temporary file using diffusers' helper
        temp_filename = "allegro_output.mp4"
        export_to_video(frames, temp_filename, fps=15)

        with open(temp_filename, "rb") as f:
            video_bytes = f.read()

        url = GriptapeNodes.StaticFilesManager().save_static_file(
            video_bytes, temp_filename
        )
        video_artifact = VideoUrlArtifact(url)

        # Publish final outputs
        self.pipe_params.publish_output_video(video_artifact)
        # Publish first frame as a convenience preview to the logs
        if frames:
            first_frame = frames[0]
            self.log_params.append_to_logs("Generated preview frame available.\n")
            self.append_value_to_parameter(
                "logs", "First frame preview attached as image artifact.\n"
            )
            # Overwrite output_video param temporarily with preview image
            # (UI frameworks usually show VideoArtifact correctly; depends on client)
            self.publish_update_to_parameter("output_video", pil_to_image_artifact(first_frame))

        self.log_params.append_to_logs("Done.\n")

        # Dump memory report
        logger.info("Allegro memory footprint after inference:")
        print_allegro_pipeline_memory_footprint(pipe) 