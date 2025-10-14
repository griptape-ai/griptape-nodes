import logging

from griptape.artifacts import ImageUrlArtifact
from PIL.Image import Resampling
from utils.image_utils import load_image_from_url_artifact

from griptape_nodes.exe_types.core_types import NodeMessageResult, Parameter, ParameterMessage, ParameterMode
from griptape_nodes.exe_types.node_types import AsyncResult, ControlNode
from griptape_nodes.retained_mode.events.parameter_events import (
    ConversionConfig,
)
from griptape_nodes.retained_mode.retained_mode import RetainedMode as cmd  # noqa: N813
from griptape_nodes.traits.button import Button, ButtonDetailsMessagePayload
from griptape_nodes.traits.options import Options
from pillow_nodes_library.utils import (  # type: ignore[reportMissingImports]
    image_artifact_to_pil,  # type: ignore[reportMissingImports]
    pil_to_image_artifact,  # type: ignore[reportMissingImports]
)

logger = logging.getLogger("pillow_nodes_library")


class RescaleImage(ControlNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.migrate_message = ParameterMessage(
            variant="warning",
            full_width=True,
            button_text="Create Rescale Image Node",
            value="This node is being deprecated.\nPlease use the Rescale Image node from the Griptape Nodes Library.",
            traits={
                Button(label="Create Rescale Image Node", icon="plus", variant="secondary", on_click=self._migrate)
            },
        )
        self.add_node_element(self.migrate_message)

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
                name="scale",
                default_value=2.0,
                input_types=["float"],
                type="float",
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

    def _migrate(self, button: Button, button_details: ButtonDetailsMessagePayload) -> NodeMessageResult | None:  # noqa: ARG002
        # Create the new node positioned relative to this one
        new_node_name = f"{self.name}_migrated"

        # Create the new node positioned above this one
        new_node_result = cmd.create_node_relative_to(
            reference_node_name=self.name,
            new_node_type="RescaleImage",
            new_node_name=new_node_name,
            specific_library_name="Griptape Nodes Library",
            offset_side="top_left",
            offset_y=-1056,  # Negative offset to go UP from the reference node's top-left corner
            swap=True,
        )

        # Extract the node name from the result
        if isinstance(new_node_result, str):
            new_node = new_node_result
        else:
            # If create_node_relative_to failed, new_node_result is the error result
            logger.error("Failed to create node: %s", new_node_result)
            return None

        # Migrate executions
        cmd.migrate_parameter(self.name, new_node, "exec_in", "exec_in")
        cmd.migrate_parameter(self.name, new_node, "exec_out", "exec_out")

        # Migrate simple parameters (no conversion needed)
        cmd.migrate_parameter(self.name, new_node, "input_image", "input_image")
        cmd.migrate_parameter(self.name, new_node, "resample_strategy", "resample_filter")
        cmd.migrate_parameter(self.name, new_node, "output_image", "output")

        # Migrate scale parameter with conversion (0.0-1.0 → 0-100)
        cmd.migrate_parameter(
            source_node_name=self.name,
            target_node_name=new_node,
            source_parameter_name="scale",
            target_parameter_name="percentage_scale",
            input_conversion=ConversionConfig(
                library="Griptape Nodes Library",
                node_type="Math",
                input_parameter="A",
                output_parameter="result",
                additional_parameters={
                    "operation": "multiply [A * B]",
                    "B": 100,
                },
                offset_x=-573,
                offset_y=150,
            ),
            output_conversion=ConversionConfig(
                library="Griptape Nodes Library",
                node_type="Math",
                input_parameter="A",
                output_parameter="result",
                additional_parameters={
                    "operation": "divide [A / B]",
                    "B": 100,
                },
                offset_x=250,
                offset_y=150,
            ),
            value_transform=self._scale_transform,
        )

        return None

    def _scale_transform(self, x: float) -> float:
        return x * 100

    def process(self) -> AsyncResult | None:
        yield lambda: self._process()

    def _process(self) -> AsyncResult | None:
        input_image_artifact = self.get_parameter_value("input_image")
        scale = float(self.get_parameter_value("scale"))
        resample_strategy = str(self.get_parameter_value("resample_strategy"))

        if isinstance(input_image_artifact, ImageUrlArtifact):
            input_image_artifact = load_image_from_url_artifact(input_image_artifact)

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
