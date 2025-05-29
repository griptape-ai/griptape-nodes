import logging

import PIL.Image

# TODO: https://github.com/griptape-ai/griptape-nodes/issues/829
from diffusers_nodes_library.common.misc.tiling_image_processor import (
    TilingImageProcessor,  # type: ignore[reportMissingImports]
)
from diffusers_nodes_library.common.parameters.huggingface_repo_file_parameter import (
    HuggingFaceRepoFileParameter,  # type: ignore[reportMissingImports]
)
from diffusers_nodes_library.common.parameters.log_parameter import (  # type: ignore[reportMissingImports]
    LogParameter,  # type: ignore[reportMissingImports]
)
from griptape.artifacts import ImageUrlArtifact
from griptape.loaders import ImageLoader
from PIL.Image import Image
from pillow_nodes_library.utils import (  # type: ignore[reportMissingImports]
    image_artifact_to_pil,
    pil_to_image_artifact,
)

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import AsyncResult, ControlNode
from griptape_nodes.traits.options import Options
from spandrel_nodes_library.utils import SpandrelPipeline  # type: ignore[reportMissingImports]

logger = logging.getLogger("spandrel_nodes_library")


class TilingSPAN(ControlNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        repo_file = self.get_repo_id(), self.get_filename()
        self._huggingface_repo_file_parameter = HuggingFaceRepoFileParameter(
            self, repo_files=[repo_file], parameter_name="lora_model"
        )

        self.log_params = LogParameter(self)

        self._huggingface_repo_file_parameter.add_input_parameters()
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
                name="max_tile_size",
                default_value=256,
                input_types=["int"],
                type="int",
                tooltip=(
                    "max_tile_size, "
                    "if unecessily larger than input image, it will automatically "
                    "be lowered to fit the input image as tightly as possible"
                ),
            )
        )
        self.add_parameter(
            Parameter(
                name="tile_overlap",
                default_value=16,
                input_types=["int"],
                type="int",
                tooltip="tile_overlap",
            )
        )
        self.add_parameter(
            Parameter(
                name="tile_strategy",
                default_value="linear",
                input_types=["str"],
                type="str",
                traits={
                    Options(
                        choices=[
                            "linear",
                            "chess",
                            "random",
                            "inward",
                            "outward",
                        ]
                    )
                },
                tooltip="tile_strategy",
            )
        )
        # TODO: https://github.com/griptape-ai/griptape-nodes/issues/832
        self.add_parameter(
            Parameter(
                name="output_image",
                output_type="ImageUrlArtifact",
                tooltip="The output image",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        self.log_params.add_output_parameters()

    def get_repo_id(self) -> str:
        return "skbhadra/ClearRealityV1"

    def get_filename(self) -> str:
        return "4x-ClearRealityV1.pth"

    def validate_before_node_run(self) -> list[Exception] | None:
        errors = self._huggingface_repo_file_parameter.validate_before_node_run()
        return errors or None

    def process(self) -> AsyncResult | None:
        yield lambda: self._process()

    def _process(self) -> AsyncResult | None:
        input_image_artifact = self.get_parameter_value("input_image")

        max_tile_size = int(self.get_parameter_value("max_tile_size"))
        tile_overlap = int(self.get_parameter_value("tile_overlap"))
        tile_strategy = str(self.get_parameter_value("tile_strategy"))

        if isinstance(input_image_artifact, ImageUrlArtifact):
            input_image_artifact = ImageLoader().parse(input_image_artifact.to_bytes())
        input_image_pil = image_artifact_to_pil(input_image_artifact)
        input_image_pil = input_image_pil.convert("RGB")

        output_scale = 4  # THIS IS SPECIFIC TO 4x-ClearRealityV1 - TODO(dylan): Make per-model configurable

        # The output image will be the scaled by output_scale compared to the input image.
        # Immediately set a preview placeholder image to make it react quickly and adjust
        # the size of the image preview on the node.
        w, h = input_image_pil.size
        ow, oh = int(w * output_scale), int(h * output_scale)
        preview_placeholder_image = PIL.Image.new("RGB", (ow, oh), color="black")
        self.publish_update_to_parameter("output_image", pil_to_image_artifact(preview_placeholder_image))

        # Adjust tile size so that it is not much bigger than the input image.
        largest_reasonable_tile_size = max(input_image_pil.height, input_image_pil.width)
        tile_size = min(largest_reasonable_tile_size, max_tile_size)

        with self.log_params.append_profile_to_logs("Loading model metadata"):
            repo, revision = self._huggingface_repo_file_parameter.get_repo_revision()
            pipe = SpandrelPipeline.from_hf_file(repo_id=repo, revision=revision, filename=self.get_filename())

        tiling_image_processor = TilingImageProcessor(
            pipe=pipe,
            tile_size=tile_size,
            tile_overlap=tile_overlap,
            tile_strategy=tile_strategy,
        )
        num_tiles = tiling_image_processor.get_num_tiles(image=input_image_pil)

        def callback_on_tile_end(i: int, preview_image_pil: Image) -> None:
            if i < num_tiles:
                self.publish_update_to_parameter("output_image", pil_to_image_artifact(preview_image_pil))
                self.log_params.append_to_logs(f"Finished tile {i} of {num_tiles}.\n")
                self.log_params.append_to_logs(f"Starting tile {i + 1} of {num_tiles}...\n")

        self.log_params.append_to_logs(f"Starting tile 1 of {num_tiles}...\n")
        output_image_pil = tiling_image_processor.process(
            image=input_image_pil,
            output_scale=output_scale,
            callback_on_tile_end=callback_on_tile_end,
        )
        self.log_params.append_to_logs(f"Finished tile {num_tiles} of {num_tiles}.\n")
        self.parameter_output_values["output_image"] = pil_to_image_artifact(output_image_pil)
