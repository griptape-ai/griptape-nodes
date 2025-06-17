import hashlib
import logging
import re
from typing import Any

import safetensors  # type: ignore[reportMissingImports]

from griptape_nodes.exe_types.core_types import ParameterList, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode

logger = logging.getLogger("diffusers_nodes_library")


class WanLorasParameter:
    def __init__(self, node: BaseNode):
        self._node = node
        self._loras_parameter_name = "loras"

    def add_input_parameters(self) -> None:
        self._node.add_parameter(
            ParameterList(
                name="loras",
                input_types=["loras", "dict"],
                default_value=[],
                type="loras",
                allowed_modes={ParameterMode.INPUT, ParameterMode.OUTPUT},
                tooltip="loras",
            )
        )

    def to_adapter_name(self, model_path: str) -> str:
        """Returns a unique name for an adapter given its model path."""
        return hashlib.sha256(model_path.encode("utf-8")).hexdigest()

    def configure_loras(self, pipe: Any) -> None:
        loras_list = self._node.get_parameter_value(self._loras_parameter_name) or []

        loras = {}
        for lora in loras_list:
            loras.update(lora)

        if not loras:
            pipe.disable_lora()
            return

        lora_by_name = {
            self.to_adapter_name(k): {"name": self.to_adapter_name(k), "path": k, "weight": float(v)}
            for k, v in loras.items()
        }

        loras_to_load = dict(lora_by_name)
        existing_adapter_names = {name for names in pipe.get_list_adapters().values() for name in names}
        for name in existing_adapter_names:
            if name in loras_to_load:
                # Don't reload existing loras.
                loras_to_load.pop(name)

        # Load the loras.
        for item in loras_to_load.values():
            lora_path = item["path"]
            logger.info("Loading lora weights: %s", lora_path)
            state_dict = safetensors.torch.load_file(lora_path)  # type: ignore[reportAttributeAccessIssue]

            # Fix for loading Wan 2.1 loras with Wan VACE
            #
            # When attempting to load a wan lora with vace, we are getting some incorrect layer mappings, which is causing
            # an at first seemingly unrelated error when trying to run the pipeline (complains about meta device).
            # Specifically the proj_out.* layers in the lora are getting mapped to the base transformer proj_out layers
            # AND the vace proj_out layers. They should only be mapped to the vace layers.
            # According to https://github.com/huggingface/peft/pull/2419, you can prefix the keys with "^" to avoid
            # mapping to all matches.
            # So, we replace the keys that start with "proj_out" with "^proj_out" to avoid adding them to the
            # vace_block layers.
            # Note that we also need to rename the keys that will be loaded. In case the lora is not already in diffusers format,
            # we need to convert it to diffusers format first, which is done by calling `pipe.lora_state_dict(state_dict)`.
            state_dict = pipe.lora_state_dict(state_dict)
            for key in list(state_dict.keys()):
                if key.startswith("transformer.proj_out."):
                    new_key = "^" + key
                    state_dict[new_key] = state_dict.pop(key)
                    logger.info("Renamed %s to %s in lora state_dict to avoid mapping to vace layers.", key, new_key)

            # Load the lora weights into the pipeline.
            pipe.load_lora_weights(state_dict, adapter_name=item["name"])

        # Use them with given weights.
        adapter_names = [v["name"] for v in lora_by_name.values()]
        adapter_weights = [v["weight"] for v in lora_by_name.values()]
        msg = f"Using adapter_names with weights:\n{adapter_names=}\n{adapter_weights=}"
        logger.info(msg)
        pipe.set_adapters(adapter_names=adapter_names, adapter_weights=adapter_weights)
        pipe.enable_lora()


# This is unused, but keeping because it is very useful for debugging lora loading issues.
def log_cleaned_state_dict_keys(state_dict: dict) -> None:
    """Logs all keys in the state_dict, replacing numbers with '<NUM>' for brevity."""
    pattern = re.compile(r"\b\d+\b")
    cleaned_keys = set()

    for key in state_dict:
        cleaned_key = pattern.sub("<NUM>", key)
        cleaned_keys.add(cleaned_key)

    for key in sorted(cleaned_keys):
        logger.info(key)


# This is unused, but keeping because it is very useful for debugging lora loading issues.
def extract_lora_state_dict(model: Any) -> dict:
    """Extracts a state_dict containing only LoRA-related parameters from the model.

    Looks for parameter names containing 'lora_'.
    """
    lora_state_dict = {name: param for name, param in model.named_parameters() if "lora_" in name}
    return lora_state_dict
