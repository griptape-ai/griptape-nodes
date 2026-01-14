import logging
from typing import Any

import PIL.Image
import torch  # type: ignore[reportMissingImports]
from diffusers.pipelines.pipeline_utils import DiffusionPipeline  # type: ignore[reportMissingImports]
from griptape.artifacts import ImageUrlArtifact
from PIL.Image import Image
from pillow_nodes_library.utils import image_artifact_to_pil, pil_to_image_artifact  # type: ignore[reportMissingImports]
from utils.image_utils import load_image_from_url_artifact

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode
from griptape_nodes.exe_types.param_components.seed_parameter import SeedParameter

logger = logging.getLogger("diffusers_nodes_library")


class MarigoldIntrinsicsPipelineRuntimeParameters:
    def __init__(self, node: BaseNode):
        self._node = node
        self._seed_parameter = SeedParameter(node)

    def add_input_parameters(self) -> None:
        self._node.add_parameter(
            Parameter(
                name="image",
                input_types=["ImageArtifact", "ImageUrlArtifact"],
                type="ImageArtifact",
                tooltip="Input image for intrinsic image decomposition.",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="num_inference_steps",
                default_value=4,
                type="int",
                tooltip="The number of denoising steps.",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="ensemble_size",
                default_value=1,
                type="int",
                tooltip="Number of ensemble predictions. Higher values improve quality but increase processing time.",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="processing_resolution",
                default_value=0,
                type="int",
                tooltip="Resolution for processing. 0 uses native input resolution.",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="match_input_resolution",
                default_value=True,
                type="bool",
                tooltip="Resize output to match input dimensions.",
            )
        )
        self._seed_parameter.add_input_parameters()

    def add_output_parameters(self) -> None:
        self._node.add_parameter(
            Parameter(
                name="albedo",
                output_type="ImageArtifact",
                tooltip="Albedo (base color) output",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        self._node.add_parameter(
            Parameter(
                name="component_1",
                output_type="ImageArtifact",
                tooltip="Second intrinsic component (roughness for appearance model, shading for lighting model)",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        self._node.add_parameter(
            Parameter(
                name="component_2",
                output_type="ImageArtifact",
                tooltip="Third intrinsic component (metallicity for appearance model, residual for lighting model)",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

    def remove_input_parameters(self) -> None:
        self._node.remove_parameter_element_by_name("image")
        self._node.remove_parameter_element_by_name("num_inference_steps")
        self._node.remove_parameter_element_by_name("ensemble_size")
        self._node.remove_parameter_element_by_name("processing_resolution")
        self._node.remove_parameter_element_by_name("match_input_resolution")
        self._seed_parameter.remove_input_parameters()

    def remove_output_parameters(self) -> None:
        self._node.remove_parameter_element_by_name("albedo")
        self._node.remove_parameter_element_by_name("component_1")
        self._node.remove_parameter_element_by_name("component_2")

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        self._seed_parameter.after_value_set(parameter, value)

    def preprocess(self) -> None:
        self._seed_parameter.preprocess()

    def get_image_pil(self) -> Image:
        input_image_artifact = self._node.get_parameter_value("image")
        if input_image_artifact is None:
            msg = f"{self._node.name} requires an input image"
            logger.error(msg)
            raise ValueError(msg)

        if isinstance(input_image_artifact, ImageUrlArtifact):
            input_image_artifact = load_image_from_url_artifact(input_image_artifact)
        input_image_pil = image_artifact_to_pil(input_image_artifact)
        return input_image_pil.convert("RGB")

    def get_num_inference_steps(self) -> int:
        return int(self._node.get_parameter_value("num_inference_steps"))

    def get_pipe_kwargs(self) -> dict:
        return {
            "image": self.get_image_pil(),
            "num_inference_steps": self.get_num_inference_steps(),
            "ensemble_size": self._node.get_parameter_value("ensemble_size"),
            "processing_resolution": self._node.get_parameter_value("processing_resolution"),
            "match_input_resolution": self._node.get_parameter_value("match_input_resolution"),
            "generator": torch.Generator().manual_seed(self._seed_parameter.get_seed()),
            "output_type": "np",
        }

    def publish_output_image_preview_placeholder(self) -> None:
        input_image = self.get_image_pil()
        width, height = input_image.size
        preview_placeholder_image = PIL.Image.new("RGB", (width, height), color="black")
        placeholder_artifact = pil_to_image_artifact(preview_placeholder_image)
        self._node.publish_update_to_parameter("albedo", placeholder_artifact)
        self._node.publish_update_to_parameter("component_1", placeholder_artifact)
        self._node.publish_update_to_parameter("component_2", placeholder_artifact)

    def process_pipeline(self, pipe: DiffusionPipeline) -> None:
        self._node.log_params.append_to_logs("Running Marigold intrinsic image decomposition...\n")  # type: ignore[reportAttributeAccessIssue]

        num_inference_steps = self.get_num_inference_steps()
        ensemble_size = self._node.get_parameter_value("ensemble_size")
        total_steps = num_inference_steps * ensemble_size
        self._node.progress_bar_component.initialize(total_steps)  # type: ignore[reportAttributeAccessIssue]

        step_count = 0

        def callback_on_step_end(
            _pipe: DiffusionPipeline,
            _i: int,
            _t: int,
            callback_kwargs: dict,
        ) -> dict:
            nonlocal step_count
            if self._node.is_cancellation_requested:
                _pipe._interrupt = True
                self._node.log_params.append_to_logs("Cancellation requested, stopping...\n")  # type: ignore[reportAttributeAccessIssue]
                return callback_kwargs

            step_count += 1
            self._node.progress_bar_component.increment()  # type: ignore[reportAttributeAccessIssue]
            self._node.log_params.append_to_logs(f"Step {step_count} of {total_steps}\n")  # type: ignore[reportAttributeAccessIssue]
            return {}

        pipe_kwargs = self.get_pipe_kwargs()
        pipe_kwargs["callback_on_step_end"] = callback_on_step_end

        with torch.inference_mode():
            result = pipe(**pipe_kwargs)

        prediction = result.prediction
        target_properties = pipe.target_properties

        vis_list = pipe.image_processor.visualize_intrinsics(prediction, target_properties)

        if vis_list:
            vis_dict = vis_list[0]

            if "albedo" in vis_dict:
                self.publish_output_image("albedo", vis_dict["albedo"])

            if "roughness" in vis_dict:
                self.publish_output_image("component_1", vis_dict["roughness"])
                self._node.log_params.append_to_logs("Output component_1: roughness\n")  # type: ignore[reportAttributeAccessIssue]
            elif "shading" in vis_dict:
                self.publish_output_image("component_1", vis_dict["shading"])
                self._node.log_params.append_to_logs("Output component_1: shading\n")  # type: ignore[reportAttributeAccessIssue]

            if "metallicity" in vis_dict:
                self.publish_output_image("component_2", vis_dict["metallicity"])
                self._node.log_params.append_to_logs("Output component_2: metallicity\n")  # type: ignore[reportAttributeAccessIssue]
            elif "residual" in vis_dict:
                self.publish_output_image("component_2", vis_dict["residual"])
                self._node.log_params.append_to_logs("Output component_2: residual\n")  # type: ignore[reportAttributeAccessIssue]

        self._node.log_params.append_to_logs("Done.\n")  # type: ignore[reportAttributeAccessIssue]

    def publish_output_image(self, param_name: str, output_image_pil: Image) -> None:
        image_artifact = pil_to_image_artifact(output_image_pil)
        self._node.publish_update_to_parameter(param_name, image_artifact)
        self._node.set_parameter_value(param_name, image_artifact)
        self._node.parameter_output_values[param_name] = image_artifact

    def validate_before_node_run(self) -> list[Exception] | None:
        errors = []
        image_artifact = self._node.get_parameter_value("image")
        if image_artifact is None:
            errors.append(ValueError(f"{self._node.name} requires an input image"))

        if errors:
            return errors
        return None
