import hashlib
import logging

import diffusers  # type: ignore[reportMissingImports]
import safetensors  # type: ignore[reportMissingImports]
import torch  # type: ignore[reportMissingImports]
import torch.nn.functional  # type: ignore[reportMissingImports]

from diffusers_nodes_library.utils.torch_utils import get_best_device  # type: ignore[reportMissingImports]
from griptape_nodes.exe_types.node_types import ControlNode

logger = logging.getLogger("diffusers_nodes_library")


def to_adapter_name(model_path: str) -> str:
    """Returns a unique name for an adapter given its model path."""
    return hashlib.sha256(model_path.encode("utf-8")).hexdigest()


def configure_flux_loras(node: ControlNode, pipe: diffusers.FluxPipeline, loras: dict[str, str]) -> None:
    """Configure loras for diffusers pipeline."""
    if not loras:
        pipe.disable_lora()
        return

    lora_by_name = {
        to_adapter_name(k): {"name": to_adapter_name(k), "path": k, "weight": float(v)} for k, v in loras.items()
    }

    loras_to_load = dict(lora_by_name)
    existing_adapter_names = {name for names in pipe.get_list_adapters().values() for name in names}
    for name in existing_adapter_names:
        # Don't reload existing loras.
        loras_to_load.pop(name)

    # Load the loras.
    for item in loras_to_load.values():
        lora_path = item["path"]
        msg = f"Loading lora weights: {lora_path}"
        logger.info(msg)
        node.append_value_to_parameter("logs", f"{msg}\n")
        state_dict = safetensors.torch.load_file(lora_path)
        pipe.load_lora_weights(state_dict, adapter_name=item["name"])

    if loras_to_load and get_best_device(quiet=True) == torch.device("cuda"):
        # If we loaded any loras, make sure the layers have been casted
        # to bfloat16. For cuda, we enable the layerwise caching on the
        # transformer, but this isn't applied to the linear layers added
        # by the loras. Those are loaded as fp8, and cuda doesn't have
        # all the right matrix operation kernels for fp8, so we need to
        # cast to bfloat16. That's fine because there are a lot less lora
        # weights when compared to the original transformer (so it won't
        # take up that much space on the device).
        # TODO: https://github.com/griptape-ai/griptape-nodes/issues/849
        logger.info("converting all lora_A and lora_B layers to bfloat16")
        lora_modules = [
            module
            for name, module in pipe.transformer.named_modules()
            if hasattr(module, "lora_A") or hasattr(module, "lora_B")
        ]

        logger.info("Converting %d lora related layers to bfloat16", len(lora_modules))
        for module in lora_modules:
            module.to(dtype=torch.bfloat16)

    # Use them with given weights.
    adapter_names = [v["name"] for v in lora_by_name.values()]
    adapter_weights = [v["weight"] for v in lora_by_name.values()]
    msg = f"Using adapter_names with weights:\n{adapter_names=}\n{adapter_weights=}"
    logger.info(msg)
    node.append_value_to_parameter("logs", f"{msg}\n")
    pipe.set_adapters(adapter_names=adapter_names, adapter_weights=adapter_weights)
    pipe.enable_lora()
