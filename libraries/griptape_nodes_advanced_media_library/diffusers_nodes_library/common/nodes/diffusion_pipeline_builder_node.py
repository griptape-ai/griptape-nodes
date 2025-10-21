import hashlib
import json
import logging
from typing import Any

from diffusers_nodes_library.common.parameters.diffusion.builder_parameters import (
    DiffusionPipelineBuilderParameters,
)
from diffusers_nodes_library.common.parameters.huggingface_pipeline_parameter import HuggingFacePipelineParameter
from diffusers_nodes_library.common.utils.huggingface_utils import model_cache
from diffusers_nodes_library.common.utils.lora_utils import LorasParameter
from diffusers_nodes_library.common.utils.pipeline_utils import optimize_diffusion_pipeline
from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.exe_types.node_types import AsyncResult, ControlNode, NodeResolutionState
from griptape_nodes.exe_types.param_components.log_parameter import LogParameter
from griptape_nodes.retained_mode.events.parameter_events import SetParameterValueRequest
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

logger = logging.getLogger("diffusers_nodes_library")

# Additional postfix bits must be powers of two (1, 2, 4, 8, etc.) to ensure unique combinations
UNION_PRO_2_CONFIG_HASH_POSTFIX = 1  # 0001


class DiffusionPipelineBuilderNode(ControlNode):
    def __init__(self, **kwargs) -> None:
        self._initializing = True
        self.param_names_cache: set[str] = set()
        self.param_attrs_cache: dict[str, dict[str, Any]] = {}  # Cache parameter attributes for restoration
        super().__init__(**kwargs)
        self.params = DiffusionPipelineBuilderParameters(self)
        self.huggingface_pipeline_params = HuggingFacePipelineParameter(self)
        self.log_params = LogParameter(self)

        self.params.add_output_parameters()
        self.params.add_input_parameters()
        self.huggingface_pipeline_params.add_input_parameters()

        self.loras_params = LorasParameter(self)
        self.loras_params.add_input_parameters()

        self.log_params.add_output_parameters()

        self._initializing = False

    @property
    def state(self) -> NodeResolutionState:
        """Overrides BaseNode.state @property to compute state based on pipeline's existence in model_cache, ensuring pipeline rebuild if missing."""
        if self._state == NodeResolutionState.RESOLVED and not model_cache.has_pipeline(
            self.get_parameter_value("pipeline")
        ):
            logger.debug("Pipeline not found in cache, marking node as UNRESOLVED")
            return NodeResolutionState.UNRESOLVED
        return super().state

    @state.setter
    def state(self, new_state: NodeResolutionState) -> None:
        self._state = new_state

    def set_config_hash(self) -> None:
        config_hash = self._config_hash
        self.log_params.append_to_logs(f"Pipeline configuration hash: {config_hash}\n")
        GriptapeNodes.handle_request(
            SetParameterValueRequest(parameter_name="pipeline", value=config_hash, node_name=self.name)
        )

    @property
    def optimization_kwargs(self) -> dict[str, Any]:
        """Get optimization settings for the pipeline."""
        return self.huggingface_pipeline_params.get_hf_pipeline_parameters()

    def _get_config_hash_postfix(self) -> int:
        config_bits = 0
        controlnet_model = self.get_parameter_value("controlnet_model")
        if controlnet_model and controlnet_model.startswith("Shakker-Labs/FLUX.1-dev-ControlNet-Union-Pro-2.0"):
            # Set the UNION_PRO_2_CONFIG_HASH_POSTFIX bit
            config_bits |= UNION_PRO_2_CONFIG_HASH_POSTFIX
        return config_bits

    @property
    def _config_hash(self) -> str:
        """Generate a hash for the current configuration to use as cache key."""
        config_data = {
            **self.params.get_config_kwargs(),
            **self.loras_params.get_loras(),
            "torch_dtype": "bfloat16",  # Currently hardcoded
        }

        opt_kwargs = self.huggingface_pipeline_params.get_hf_pipeline_parameters()
        for key, value in opt_kwargs.items():
            config_data[f"opt_{key}"] = value

        config_hash = (
            self.params.pipeline_type_parameters.pipeline_type_pipeline_params.pipeline_name
            + "-"
            + hashlib.sha256(json.dumps(config_data, sort_keys=True).encode()).hexdigest()
        )
        # Convert to hex and append postfix bits
        config_hash += f"-{self._get_config_hash_postfix():x}"
        return config_hash

    def add_parameter(self, parameter: Parameter) -> None:
        """Add a parameter to the node.

        During initialization, parameters are added normally.
        After initialization (dynamic mode), parameters are marked as user-defined
        for serialization and duplicates are prevented.
        """
        if self._initializing:
            super().add_parameter(parameter)
            return

        # Dynamic mode: prevent duplicates and mark as user-defined
        if not self.does_name_exist(parameter.name):
            parameter.user_defined = True

            # Restore cached parameter attributes if available
            if parameter.name in self.param_attrs_cache:
                cached_attrs = self.param_attrs_cache[parameter.name]
                # Restore important attributes that users might have modified
                if "allowed_modes" in cached_attrs:
                    parameter._allowed_modes = cached_attrs["allowed_modes"]
                if "ui_options" in cached_attrs:
                    # Only restore specific ui_options that users can modify
                    ui_options_to_restore = {"hide"}
                    parameter.ui_options = {
                        **parameter.ui_options,
                        **{k: v for k, v in cached_attrs["ui_options"].items() if k in ui_options_to_restore},
                    }

            super().add_parameter(parameter)

    def set_parameter_value(
        self,
        param_name: str,
        value: Any,
        *,
        initial_setup: bool = False,
        emit_change: bool = True,
        skip_before_value_set: bool = False,
    ) -> None:
        parameter = self.get_parameter_by_name(param_name)
        if parameter is None:
            return
        self.params.before_value_set(parameter, value)

        super().set_parameter_value(
            param_name,
            value,
            initial_setup=initial_setup,
            emit_change=emit_change,
            skip_before_value_set=skip_before_value_set,
        )

        self.params.after_value_set(parameter, value)
        self.huggingface_pipeline_params.after_value_set(parameter, value)
        if parameter.name != "pipeline":
            self.set_config_hash()

    def validate_before_node_run(self) -> list[Exception] | None:
        return self.params.pipeline_type_parameters.pipeline_type_pipeline_params.validate_before_node_run()

    def preprocess(self) -> None:
        self.log_params.clear_logs()

    def save_param_attrs(self) -> None:
        """Save important parameter attributes to cache before removal."""
        for element in self.root_ui_element.children:
            parameter = self.get_parameter_by_name(element.name)
            if parameter is not None:
                # Cache attributes that users might have modified
                self.param_attrs_cache[parameter.name] = {
                    "allowed_modes": parameter._allowed_modes.copy(),
                    "ui_options": parameter.ui_options.copy() if parameter.ui_options else {},
                }

    def clear_param_attrs_cache(self) -> None:
        """Clear the parameter attributes cache."""
        self.param_attrs_cache.clear()

    def remove_parameter_element_by_name(self, name: str) -> None:
        """Override to track parameter deletions for connection preservation."""
        # Cache this parameter name before deletion
        self.param_names_cache.add(name)
        # Call parent implementation to actually remove it
        super().remove_parameter_element_by_name(name)

    def save_param_names(self, param_names: set[str]) -> None:
        """Add parameter names to cache (accumulative)."""
        self.param_names_cache.update(param_names)

    def get_cached_param_names(self) -> set[str]:
        """Get cached parameter names."""
        return self.param_names_cache

    def clear_param_names_cache(self) -> None:
        """Clear the parameter names cache."""
        self.param_names_cache.clear()

    def process(self) -> AsyncResult:
        self.preprocess()
        self.log_params.append_to_logs("Building pipeline...\n")

        def builder() -> Any:
            return self._build_pipeline()

        with self.log_params.append_profile_to_logs("Pipeline building/caching"):
            yield lambda: model_cache.get_or_build_pipeline(self.get_parameter_value("pipeline"), builder)

        self.log_params.append_to_logs("Pipeline building complete.\n")

    def _build_pipeline(self) -> Any:
        """Build the actual pipeline instance."""
        self.log_params.append_to_logs("Creating new pipeline instance...\n")

        with self.log_params.append_profile_to_logs("Loading pipeline"):
            pipe = self.params.pipeline_type_parameters.pipeline_type_pipeline_params.build_pipeline()

        with self.log_params.append_profile_to_logs("Configuring FLUX loras"):
            self.loras_params.configure_loras(pipe)

        with self.log_params.append_profile_to_logs("Applying optimizations"):
            optimization_kwargs = self.huggingface_pipeline_params.get_hf_pipeline_parameters()
            optimize_diffusion_pipeline(pipe=pipe, **optimization_kwargs)

        self.log_params.append_to_logs("Pipeline creation complete.\n")
        return pipe
