import logging
from collections.abc import Iterator
from typing import ClassVar

import controlnet_aux  # type: ignore[reportMissingImports]

import PIL.Image
import torch  # type: ignore[reportMissingImports]
from diffusers_nodes_library.utils.huggingface_utils import (  # type: ignore[reportMissingImports]
    list_repo_revisions_in_cache,  # type: ignore[reportMissingImports]
)
from diffusers_nodes_library.utils.logging_utils import StdoutCapture  # type: ignore[reportMissingImports]
from griptape.artifacts import ImageUrlArtifact
from griptape.loaders import ImageLoader
from PIL.Image import Image
from pillow_nodes_library.utils import (  # type: ignore[reportMissingImports]
    image_artifact_to_pil,  # type: ignore[reportMissingImports]
    pil_to_image_artifact,  # type: ignore[reportMissingImports]
)

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import AsyncResult, ControlNode
from griptape_nodes.traits.options import Options
import huggingface_hub
logger = logging.getLogger("diffusers_nodes_library")

REPO_IDS = [
    "TheMistoAI/MistoLine",
]


class AnylineDetector(ControlNode):
    _pipes: ClassVar[dict[str, controlnet_aux.AnylineDetector]] = {}  # type: ignore[reportAttributeAccessIssue]

    @classmethod
    def _get_pipe(cls, repo_id: str, revision: str) -> controlnet_aux.AnylineDetector:  # type: ignore[reportAttributeAccessIssue]
        key = AnylineDetector._repo_revision_to_key((repo_id, revision))
        if key not in cls._pipes:
            if repo_id not in REPO_IDS:
                logger.exception("Repo id %s not supported by %s", repo_id, cls.__name__)

            model_path = huggingface_hub.hf_hub_download(
                repo_id=repo_id, revision=revision, filename="MTEED.pth", subfolder="Anyline", local_files_only=True
            )
            model = controlnet_aux.teed.ted.TED()
            model.load_state_dict(torch.load(model_path, map_location="cpu"))
            anyline = controlnet_aux.AnylineDetector(model=model)

            def pipe(input_image_pil: Image) -> Image:
                return anyline(input_image_pil)

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

        self.category = "image"
        self.description = "AnylineDetector"

        self.add_parameter(
            Parameter(
                name="model",
                default_value=(
                    AnylineDetector._repo_revision_to_key(self.repo_revisions[0])
                    if self.repo_revisions
                    else None
                ),
                input_types=["str"],
                type="str",
                traits={
                    Options(
                        choices=list(map(AnylineDetector._repo_revision_to_key, self.repo_revisions)),
                    )
                },
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                tooltip="prompt",
            )
        )
        self.add_parameter(
            Parameter(
                name="input_image",
                input_types=["ImageArtifact", "ImageUrlArtifact"],
                type="ImageArtifact",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
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

    def process(self) -> AsyncResult | None:
        yield lambda: self._process()

    def _process(self) -> AsyncResult | None:
        model = self.get_parameter_value("model")
        if model is None:
            logger.exception("No model specified")
        repo_id, revision = AnylineDetector._key_to_repo_revision(model)
        input_image_artifact = self.get_parameter_value("input_image")

        if isinstance(input_image_artifact, ImageUrlArtifact):
            input_image_artifact = ImageLoader().parse(input_image_artifact.to_bytes())
        input_image_pil = image_artifact_to_pil(input_image_artifact)
        input_image_pil = input_image_pil.convert("RGB")

        # Immediately set a preview placeholder image to make it react quickly and adjust
        # the size of the image preview on the node.
        preview_placeholder_image = PIL.Image.new("RGB", input_image_pil.size, color="black")
        self.publish_update_to_parameter("output_image", pil_to_image_artifact(preview_placeholder_image))

        pipe = self._get_pipe(repo_id, revision)

        output_image_pil = pipe(input_image_pil)
        output_image_artifact = pil_to_image_artifact(output_image_pil)

        self.set_parameter_value("output_image", output_image_artifact)
        self.parameter_output_values["output_image"] = output_image_artifact
