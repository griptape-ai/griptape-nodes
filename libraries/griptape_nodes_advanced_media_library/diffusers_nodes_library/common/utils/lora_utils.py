import hashlib
import logging
from typing import Any

import safetensors  # type: ignore[reportMissingImports]

from griptape_nodes.exe_types.core_types import ParameterList, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode

logger = logging.getLogger("diffusers_nodes_library")


class LorasParameter:
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

    def get_loras(self) -> dict[str, float]:
        loras_list = self._node.get_parameter_value(self._loras_parameter_name) or []

        loras = {}
        for lora in loras_list:
            loras.update(lora)

        return loras

    def configure_loras(self, pipe: Any) -> None:
        loras = self.get_loras()

        if not loras:
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
            msg = f"Loading lora weights: {lora_path}"
            logger.info(msg)
            state_dict = safetensors.torch.load_file(lora_path)  # type: ignore[reportAttributeAccessIssue]
            pipe.load_lora_weights(state_dict, adapter_name=item["name"])

        # Use them with given weights.
        adapter_names = [v["name"] for v in lora_by_name.values()]
        adapter_weights = [v["weight"] for v in lora_by_name.values()]
        msg = f"Using adapter_names with weights:\n{adapter_names=}\n{adapter_weights=}"
        logger.info(msg)
        pipe.set_adapters(adapter_names=adapter_names, adapter_weights=adapter_weights)

        logger.info("Fusing lora weights with diffusion model.")
        pipe.fuse_lora(adapter_names=adapter_names, lora_scale=1.0)
        pipe.unload_lora_weights()
