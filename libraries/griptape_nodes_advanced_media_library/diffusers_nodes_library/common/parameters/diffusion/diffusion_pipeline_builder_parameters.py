import hashlib
import json
import logging
from typing import Any

import diffusers  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.parameters.huggingface_pipeline_parameter import HuggingFacePipelineParameter
from diffusers_nodes_library.common.parameters.huggingface_repo_parameter import HuggingFaceRepoParameter
from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode
from griptape_nodes.traits.options import Options

logger = logging.getLogger("diffusers_nodes_library")


class DiffusionPipelineBuilderParameters:
    def __init__(self, node: BaseNode):
        self._node = node
        self._huggingface_pipeline_parameter = HuggingFacePipelineParameter(node)

        # Pipeline type to diffusers class mapping
        self._pipeline_type_mapping = {
            "basic": diffusers.FluxPipeline,
            "fill": diffusers.FluxFillPipeline,
            "kontext": diffusers.FluxKontextPipeline,
            "img2img": diffusers.FluxImg2ImgPipeline,
            "controlnet": diffusers.FluxControlNetPipeline,
            "controlnet-pro": diffusers.FluxControlNetPipeline,
            "controlnet-pro-two": diffusers.FluxControlNetPipeline,
            "diptych-fill": diffusers.FluxFillPipeline,
        }

        # Initialize repo parameters
        self._base_model_repo_parameter = HuggingFaceRepoParameter(
            node,
            repo_ids=[
                "black-forest-labs/FLUX.1-schnell",
                "black-forest-labs/FLUX.1-dev",
            ],
            parameter_name="model",
        )

        self._controlnet_repo_parameter = HuggingFaceRepoParameter(
            node,
            repo_ids=[
                "InstantX/FLUX.1-dev-Controlnet-Union",
                "XLabs-AI/flux-controlnet-canny",
                "XLabs-AI/flux-controlnet-depth",
            ],
            parameter_name="controlnet_model",
        )

    def add_input_parameters(self) -> None:
        # Provider selection (currently only Flux)
        provider_choices = ["Flux"]
        self._node.add_parameter(
            Parameter(
                name="provider",
                default_value=provider_choices[0],
                input_types=["str"],
                type="str",
                traits={Options(choices=provider_choices)},
                tooltip="AI model provider",
            )
        )

        # Pipeline type selection
        pipeline_type_choices = list(self._pipeline_type_mapping.keys())
        self._node.add_parameter(
            Parameter(
                name="pipeline_type",
                default_value=pipeline_type_choices[0],
                input_types=["str"],
                type="str",
                traits={Options(choices=pipeline_type_choices)},
                tooltip="Type of pipeline to build",
            )
        )

        # Text encoder parameters
        self._node.add_parameter(
            Parameter(
                name="text_encoder",
                input_types=["str"],
                type="str",
                allowed_modes=set(),
                tooltip="text_encoder",
                default_value="openai/clip-vit-large-patch14",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="text_encoder_2",
                input_types=["str"],
                type="str",
                allowed_modes=set(),
                tooltip="text_encoder_2",
                default_value="google/t5-v1_1-xxl",
            )
        )

        # Base model repository
        self._base_model_repo_parameter.add_input_parameters()

        # ControlNet model repository (conditional)
        self._controlnet_repo_parameter.add_input_parameters()

        # Memory optimization settings
        self._huggingface_pipeline_parameter.add_input_parameters()

        # Initially hide controlnet elements since default pipeline type doesn't use controlnet
        if not self.should_show_controlnet_params:
            self._node.hide_parameter_by_name("controlnet_model")
            self._node.hide_message_by_name("huggingface_repo_parameter_message")

    def add_output_parameters(self) -> None:
        self._node.add_parameter(
            Parameter(
                name="pipeline",
                output_type="Pipeline Config",
                default_value=None,
                tooltip="Built and cached pipeline configuration",
                allowed_modes={ParameterMode.OUTPUT},
                ui_options={"display_name": "pipeline"},
                # This will be a complex object that cannot serialize and could contain private keys; it needs to be assigned at runtime.
                serializable=False,
            )
        )

    @property
    def provider(self) -> str:
        return self._node.get_parameter_value("provider")

    @property
    def pipeline_type(self) -> str:
        return self._node.get_parameter_value("pipeline_type")

    @property
    def text_encoder(self) -> str:
        return self._node.get_parameter_value("text_encoder")

    @property
    def text_encoder_2(self) -> str:
        return self._node.get_parameter_value("text_encoder_2")

    @property
    def pipeline_class(self) -> type:
        return self._pipeline_type_mapping[self.pipeline_type]

    @property
    def repo_revision(self) -> tuple[str, str]:
        return self._base_model_repo_parameter.get_repo_revision()

    @property
    def controlnet_repo_revision(self) -> tuple[str, str] | None:
        if self.should_show_controlnet_params:
            return self._controlnet_repo_parameter.get_repo_revision()
        return None

    @property
    def should_show_controlnet_params(self) -> bool:
        return self.pipeline_type.startswith("controlnet")

    @property
    def pipeline_kwargs(self) -> dict[str, Any]:
        """Get additional kwargs for pipeline initialization."""
        kwargs = {}

        if self.should_show_controlnet_params:
            controlnet_repo_revision = self.controlnet_repo_revision
            if controlnet_repo_revision is not None:
                controlnet_repo, controlnet_revision = controlnet_repo_revision
                # ControlNet will be loaded and passed as a parameter
                kwargs["controlnet_repo"] = controlnet_repo
                kwargs["controlnet_revision"] = controlnet_revision

        return kwargs

    @property
    def optimization_kwargs(self) -> dict[str, Any]:
        """Get optimization settings for the pipeline."""
        return self._huggingface_pipeline_parameter.get_hf_pipeline_parameters()

    @property
    def config_hash(self) -> str:
        """Generate a hash for the current configuration to use as cache key."""
        config_data = {
            "provider": self.provider,
            "pipeline_type": self.pipeline_type,
            "text_encoder": self.text_encoder,
            "text_encoder_2": self.text_encoder_2,
            "model_repo": self.repo_revision[0],
            "model_revision": self.repo_revision[1],
            "torch_dtype": "bfloat16",  # Currently hardcoded
        }

        # Add controlnet config if applicable
        if self.should_show_controlnet_params:
            controlnet_repo_revision = self.controlnet_repo_revision
            if controlnet_repo_revision is not None:
                config_data["controlnet_repo"] = controlnet_repo_revision[0]
                config_data["controlnet_revision"] = controlnet_repo_revision[1]

        # Add optimization settings as individual entries
        opt_kwargs = self.optimization_kwargs
        for key, value in opt_kwargs.items():
            config_data[f"opt_{key}"] = value

        return (
            self.pipeline_class.__name__
            + "-"
            + hashlib.sha256(json.dumps(config_data, sort_keys=True).encode()).hexdigest()
        )

    def validate_configuration(self) -> list[Exception] | None:
        """Validate the current configuration."""
        errors = []

        # Validate base model
        base_errors = self._base_model_repo_parameter.validate_before_node_run()
        if base_errors:
            errors.extend(base_errors)

        # Validate controlnet model if needed
        if self.should_show_controlnet_params:
            controlnet_errors = self._controlnet_repo_parameter.validate_before_node_run()
            if controlnet_errors:
                errors.extend(controlnet_errors)

        return errors if errors else None

    def after_value_set(self, parameter: Parameter, value: Any) -> None:  # noqa: ARG002
        """Handle parameter value changes for conditional parameter visibility."""
        # Handle pipeline type changes to show/hide ControlNet parameters
        if parameter.name == "pipeline_type":
            show_controlnet = self.should_show_controlnet_params
            if show_controlnet:
                self._node.show_parameter_by_name("controlnet_model")
                self._node.show_message_by_name("huggingface_repo_parameter_message")
            else:
                self._node.hide_parameter_by_name("controlnet_model")
                self._node.hide_message_by_name("huggingface_repo_parameter_message")
