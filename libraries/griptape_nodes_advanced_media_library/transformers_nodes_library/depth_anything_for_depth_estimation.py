import contextlib
import logging
from collections.abc import Iterator
from typing import ClassVar

import PIL.Image
import torch  # type: ignore[reportMissingImports]
import transformers  # type: ignore[reportMissingImports]
from diffusers_nodes_library.common.utils.huggingface_utils import (  # type: ignore[reportMissingImports]
    list_repo_revisions_in_cache,  # type: ignore[reportMissingImports]
)
from diffusers_nodes_library.common.utils.logging_utils import StdoutCapture  # type: ignore[reportMissingImports]
from griptape.artifacts import ImageUrlArtifact
from griptape.loaders import ImageLoader
from PIL.Image import Image
from pillow_nodes_library.utils import (  # type: ignore[reportMissingImports]
    image_artifact_to_pil,  # type: ignore[reportMissingImports]
    pil_to_image_artifact,  # type: ignore[reportMissingImports]
)
from transformers import AutoImageProcessor, AutoModelForDepthEstimation  # type: ignore[reportMissingImports]

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import AsyncResult, ControlNode
from griptape_nodes.traits.options import Options

logger = logging.getLogger("diffusers_nodes_library")

REPO_IDS = [
    "depth-anything/Depth-Anything-V2-Small-hf",
    "depth-anything/Depth-Anything-V2-Large-hf",
    "depth-anything/Depth-Anything-V2-Base-hf",
    "depth-anything/Depth-Anything-V2-Metric-Outdoor-Small-hf",
    "depth-anything/Depth-Anything-V2-Metric-Outdoor-Large-hf",
    "depth-anything/Depth-Anything-V2-Metric-Outdoor-Base-hf",
    "depth-anything/Depth-Anything-V2-Metric-Indoor-Small-hf",
    "depth-anything/Depth-Anything-V2-Metric-Indoor-Base-hf",
    "depth-anything/Depth-Anything-V2-Metric-Indoor-Large-hf",
]


class DepthAnythingForDepthEstimation(ControlNode):
    _pipes: ClassVar[dict[str, transformers.DepthAnythingForDepthEstimation]] = {}  # type: ignore[reportAttributeAccessIssue]

    @classmethod
    def _get_pipe(cls, repo_id: str, revision: str) -> transformers.DepthAnythingForDepthEstimation:  # type: ignore[reportAttributeAccessIssue]
        key = DepthAnythingForDepthEstimation._repo_revision_to_key((repo_id, revision))
        if key not in cls._pipes:
            if repo_id not in REPO_IDS:
                logger.exception("Repo id %s not supported by %s", repo_id, cls.__name__)

            image_processor = AutoImageProcessor.from_pretrained(
                pretrained_model_name_or_path=repo_id, revision=revision, local_files_only=True
            )
            model = AutoModelForDepthEstimation.from_pretrained(
                pretrained_model_name_or_path=repo_id, revision=revision, local_files_only=True
            )

            def pipe(input_image_pil: Image) -> Image:
                # prepare image for the model
                inputs = image_processor(images=input_image_pil, return_tensors="pt")

                with torch.no_grad():
                    outputs = model(**inputs)

                # interpolate to original size and visualize the prediction
                post_processed_output = image_processor.post_process_depth_estimation(
                    outputs,
                    target_sizes=[(input_image_pil.height, input_image_pil.width)],
                )

                predicted_depth = post_processed_output[0]["predicted_depth"]
                depth = (predicted_depth - predicted_depth.min()) / (predicted_depth.max() - predicted_depth.min())
                depth = depth.detach().cpu().numpy() * 255
                depth = PIL.Image.fromarray(depth.astype("uint8"))

                return depth

            cls._pipes[key] = pipe

        return cls._pipes[key]

    @classmethod
    def _repo_revision_to_key(cls, repo_revision: tuple[str, str]) -> str:
        return f"{repo_revision[0]} ({repo_revision[1]})"

    @classmethod
    def _key_to_repo_revision(cls, key: str) -> tuple[str, str]:
        parts = key.rsplit(" (", maxsplit=1)
        if len(parts) != 2 or parts[1][-1] != ")":  # noqa: PLR2004
            logger.exception("Invalid key")
        return parts[0], parts[1][:-1]

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        self.repo_revisions = [
            repo_revision for repo_id in REPO_IDS for repo_revision in list_repo_revisions_in_cache(repo_id)
        ]

        self.add_parameter(
            Parameter(
                name="model",
                default_value=(
                    DepthAnythingForDepthEstimation._repo_revision_to_key(self.repo_revisions[0])
                    if self.repo_revisions
                    else None
                ),
                input_types=["str"],
                type="str",
                traits={
                    Options(
                        choices=list(map(DepthAnythingForDepthEstimation._repo_revision_to_key, self.repo_revisions)),
                    )
                },
                tooltip="prompt",
            )
        )
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
                name="output_image",
                output_type="ImageArtifact",
                tooltip="The output image",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        self.add_parameter(
            Parameter(
                name="logs",
                output_type="str",
                allowed_modes={ParameterMode.OUTPUT},
                tooltip="logs",
                ui_options={"multiline": True},
            )
        )

    def process(self) -> AsyncResult | None:
        yield lambda: self._process()

    def _process(self) -> AsyncResult | None:
        model = self.get_parameter_value("model")
        if model is None:
            logger.exception("No model specified")
        repo_id, revision = DepthAnythingForDepthEstimation._key_to_repo_revision(model)
        input_image_artifact = self.get_parameter_value("input_image")

        if isinstance(input_image_artifact, ImageUrlArtifact):
            input_image_artifact = ImageLoader().parse(input_image_artifact.to_bytes())
        input_image_pil = image_artifact_to_pil(input_image_artifact)
        input_image_pil = input_image_pil.convert("RGB")

        # Immediately set a preview placeholder image to make it react quickly and adjust
        # the size of the image preview on the node.
        preview_placeholder_image = PIL.Image.new("RGB", input_image_pil.size, color="black")
        self.publish_update_to_parameter("output_image", pil_to_image_artifact(preview_placeholder_image))

        self.append_value_to_parameter("logs", "Preparing models...\n")
        with self._append_stdout_to_logs():
            pipe = self._get_pipe(repo_id, revision)

        output_image_pil = pipe(input_image_pil)
        output_image_artifact = pil_to_image_artifact(output_image_pil)

        self.set_parameter_value("output_image", output_image_artifact)
        self.parameter_output_values["output_image"] = output_image_artifact

    @contextlib.contextmanager
    def _append_stdout_to_logs(self) -> Iterator[None]:
        def callback(data: str) -> None:
            self.append_value_to_parameter("logs", data)

        with StdoutCapture(callback):
            yield
