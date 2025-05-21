import logging
import warnings

with warnings.catch_warnings():
    warnings.simplefilter("ignore")  # Silence noisy but harmless warnings from controlnet_aux
    import controlnet_aux  # type: ignore[reportMissingImports]

import huggingface_hub
import PIL.Image
import torch  # type: ignore[reportMissingImports]
from diffusers_nodes_library.common.parameters.huggingface_repo_parameter import (
    HuggingFaceRepoParameter,  # type: ignore[reportMissingImports]
)
from griptape.artifacts import ImageUrlArtifact
from griptape.loaders import ImageLoader
from PIL.Image import Image
from pillow_nodes_library.utils import (  # type: ignore[reportMissingImports]
    image_artifact_to_pil,  # type: ignore[reportMissingImports]
    pil_to_image_artifact,  # type: ignore[reportMissingImports]
)

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import AsyncResult, ControlNode

logger = logging.getLogger("diffusers_nodes_library")


class AnylineDetector(ControlNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.category = "image"
        self.description = "AnylineDetector"
        self._huggingface_repo_parameter = HuggingFaceRepoParameter(self, repo_ids=["TheMistoAI/MistoLine"])
        self._huggingface_repo_parameter.add_input_parameters()
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

    def get_input_image(self) -> Image:
        input_image_artifact = self.get_parameter_value("input_image")
        if input_image_artifact is None:
            logger.exception("No input image specified")

        if isinstance(input_image_artifact, ImageUrlArtifact):
            input_image_artifact = ImageLoader().parse(input_image_artifact.to_bytes())
        input_image_pil = image_artifact_to_pil(input_image_artifact)
        input_image_pil = input_image_pil.convert("RGB")
        return input_image_pil

    def publish_preview_placeholder_image(self, input_image_pil: Image) -> None:
        preview_placeholder_image = PIL.Image.new("RGB", input_image_pil.size, color="black")
        self.publish_update_to_parameter("output_image", pil_to_image_artifact(preview_placeholder_image))

    def get_anyline(self) -> controlnet_aux.AnylineDetector:
        repo_id, revision = self._huggingface_repo_parameter.get_repo_revision()
        model_path = huggingface_hub.hf_hub_download(
            repo_id=repo_id,
            revision=revision,
            filename="MTEED.pth",
            subfolder="Anyline",
            local_files_only=True,
        )
        model = controlnet_aux.teed.ted.TED()
        model.load_state_dict(torch.load(model_path, map_location="cpu"))
        return controlnet_aux.AnylineDetector(model=model)

    def process(self) -> AsyncResult | None:
        yield lambda: self._process()

    def _process(self) -> AsyncResult | None:
        input_image_pil = self.get_input_image()

        # Immediately set a preview placeholder image to make it react quickly and adjust
        # the size of the image preview on the node.
        self.publish_preview_placeholder_image(input_image_pil)

        anyline = self.get_anyline()

        output_image_pil = anyline(input_image_pil)
        output_image_artifact = pil_to_image_artifact(output_image_pil)

        self.set_parameter_value("output_image", output_image_artifact)
        self.parameter_output_values["output_image"] = output_image_artifact

    def validate_before_node_run(self) -> list[Exception] | None:
        errors = self._huggingface_repo_parameter.validate_before_node_run()
        return errors or None
