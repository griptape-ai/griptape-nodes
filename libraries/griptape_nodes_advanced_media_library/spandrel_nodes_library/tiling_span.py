import contextlib
import logging
from collections.abc import Iterator
from typing import ClassVar

import PIL.Image
from diffusers_nodes_library.utils.huggingface_utils import (
    list_repo_revisions_in_cache,  # type: ignore[reportMissingImports]
)
from diffusers_nodes_library.utils.logging_utils import StdoutCapture  # type: ignore[reportMissingImports]

# TODO: https://github.com/griptape-ai/griptape-nodes/issues/829
from diffusers_nodes_library.utils.tiling_image_processor import (
    TilingImageProcessor,  # type: ignore[reportMissingImports]
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
    _pipes: ClassVar[dict[str, SpandrelPipeline]] = {}

    @classmethod
    def _get_pipe(cls, repo_id: str, revision: str, filename: str) -> SpandrelPipeline:
        key = TilingSPAN._repo_revision_filename_to_key((repo_id, revision, filename))
        if key not in cls._pipes:
            pipe = SpandrelPipeline.from_hf_file(repo_id=repo_id, revision=revision, filename=filename)

            # Putting this on a device other than cpu is overkill I think.
            # TODO: https://github.com/griptape-ai/griptape-nodes/issues/830
            # device = get_best_device() # noqa: ERA001

            # TODO: https://github.com/griptape-ai/griptape-nodes/issues/831
            # optimize_pipe_memory_footprint(pipe) # noqa: ERA001

            cls._pipes[key] = pipe

        return cls._pipes[key]

    @classmethod
    def _repo_revision_filename_to_key(cls, repo_revision_filename: tuple[str, str, str]) -> str:
        return f"{repo_revision_filename[2]} ({repo_revision_filename[0]}, {repo_revision_filename[1]})"

    @classmethod
    def _key_to_repo_revision_filename(cls, key: str) -> tuple[str, str, str]:
        parts = key.rsplit(" (", maxsplit=1)
        if len(parts) != 2:  # noqa: PLR2004
            logger.exception("Invalid key")
        filename = parts[0]
        repo_revision = parts[1][:-1]
        parts = repo_revision.split(", ", maxsplit=1)
        if len(parts) != 2:  # noqa: PLR2004
            logger.exception("Invalid key")
        repo, revision = parts[0], parts[1]
        return repo, revision, filename

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        self.category = "image/upscale"
        self.description = "TilingSPAN node."

        repo_revisions = [
            *list_repo_revisions_in_cache("skbhadra/ClearRealityV1"),
        ]

        self.repo_revision_filenames = [
            (repo_revision[0], repo_revision[1], "4x-ClearRealityV1.pth") for repo_revision in repo_revisions
        ]

        self.add_parameter(
            Parameter(
                name="model",
                default_value=(
                    TilingSPAN._repo_revision_filename_to_key(self.repo_revision_filenames[0])
                    if self.repo_revision_filenames
                    else None
                ),
                input_types=["str"],
                type="str",
                traits={
                    Options(
                        choices=list(map(TilingSPAN._repo_revision_filename_to_key, self.repo_revision_filenames)),
                    )
                },
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                tooltip="model",
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
                name="max_tile_size",
                default_value=256,
                input_types=["int"],
                type="int",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
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
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
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
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
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
        repo, revision, filename = TilingSPAN._key_to_repo_revision_filename(model)
        input_image_artifact = self.get_parameter_value("input_image")

        max_tile_size = int(self.get_parameter_value("max_tile_size"))
        tile_overlap = int(self.get_parameter_value("tile_overlap"))
        tile_strategy = str(self.get_parameter_value("tile_strategy"))

        if isinstance(input_image_artifact, ImageUrlArtifact):
            input_image_artifact = ImageLoader().parse(input_image_artifact.to_bytes())
        input_image_pil = image_artifact_to_pil(input_image_artifact)

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

        self.append_value_to_parameter("logs", "Preparing models...\n")
        with self._append_stdout_to_logs():
            pipe = self._get_pipe(repo, revision, filename)

        def wrapped_pipe(tile: Image, *_) -> Image:
            return pipe(tile)

        tiling_image_processor = TilingImageProcessor(
            pipe=wrapped_pipe,
            tile_size=tile_size,
            tile_overlap=tile_overlap,
            tile_strategy=tile_strategy,
        )
        num_tiles = tiling_image_processor.get_num_tiles(image=input_image_pil)

        def callback_on_tile_end(i: int, preview_image_pil: Image) -> None:
            if i < num_tiles:
                self.publish_update_to_parameter("output_image", pil_to_image_artifact(preview_image_pil))
                self.append_value_to_parameter("logs", f"Finished tile {i} of {num_tiles}.\n")
                self.append_value_to_parameter("logs", f"Starting tile {i + 1} of {num_tiles}...\n")

        self.append_value_to_parameter("logs", f"Starting tile 1 of {num_tiles}...\n")
        output_image_pil = tiling_image_processor.process(
            image=input_image_pil,
            output_scale=output_scale,
            callback_on_tile_end=callback_on_tile_end,
        )
        self.append_value_to_parameter("logs", f"Finished tile {num_tiles} of {num_tiles}.\n")
        self.set_parameter_value("output_image", pil_to_image_artifact(output_image_pil))
        self.parameter_output_values["output_image"] = pil_to_image_artifact(output_image_pil)

    @contextlib.contextmanager
    def _append_stdout_to_logs(self) -> Iterator[None]:
        def callback(data: str) -> None:
            self.append_value_to_parameter("logs", data)

        with StdoutCapture(callback):
            yield
