import logging

from griptape.artifacts import ImageUrlArtifact
from griptape.loaders import ImageLoader
from PIL.Image import Resampling

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import AsyncResult, ControlNode
from griptape_nodes.traits.options import Options
from pillow_nodes_library.utils import (  # type: ignore[reportMissingImports]
    image_artifact_to_pil,  # type: ignore[reportMissingImports]
    pil_to_image_artifact,  # type: ignore[reportMissingImports]
)

logger = logging.getLogger("pillow_nodes_library")


class RescaleImage(ControlNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        self.category = "image/upscale"
        self.description = "RescaleImage node."

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
                name="scale",
                default_value=2.0,
                input_types=["float"],
                type="float",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                tooltip="scale",
            )
        )
        self.add_parameter(
            Parameter(
                name="resample_strategy",
                default_value="bicubic",
                input_types=["str"],
                type="str",
                traits={
                    Options(
                        choices=[
                            "nearest",
                            "box",
                            "bilinear",
                            "hamming",
                            "bicubic",
                            "lanczos",
                        ]
                    )
                },
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                tooltip="resample_strategy",
            )
        )
        self.add_parameter(
            Parameter(
                name="output_image",
                output_type="ImageUrlArtifact",
                tooltip="The output image",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

    def process(self) -> AsyncResult | None:
        yield lambda: self._process()

    def _process(self) -> AsyncResult | None:
        input_image_artifact = self.get_parameter_value("input_image")
        scale = float(self.get_parameter_value("scale"))
        resample_strategy = str(self.get_parameter_value("resample_strategy"))

        if isinstance(input_image_artifact, ImageUrlArtifact):
            input_image_artifact = ImageLoader().parse(input_image_artifact.to_bytes())

        input_image_pil = image_artifact_to_pil(input_image_artifact)

        resample = None
        match resample_strategy:
            case "nearest":
                resample = Resampling.NEAREST
            case "box":
                resample = Resampling.BOX
            case "bilinear":
                resample = Resampling.BILINEAR
            case "hamming":
                resample = Resampling.HAMMING
            case "bicubic":
                resample = Resampling.BICUBIC
            case "lanczos":
                resample = Resampling.LANCZOS
            case _:
                logger.exception("Unknown resampling strategy %s", resample_strategy)

        w, h = input_image_pil.size
        output_image_pil = input_image_pil.resize(
            size=(int(w * scale), int(h * scale)),
            resample=resample,
            # TODO: https://github.com/griptape-ai/griptape-nodes/issues/844
        )
        self.set_parameter_value("output_image", pil_to_image_artifact(output_image_pil))
        self.parameter_output_values["output_image"] = pil_to_image_artifact(output_image_pil)
