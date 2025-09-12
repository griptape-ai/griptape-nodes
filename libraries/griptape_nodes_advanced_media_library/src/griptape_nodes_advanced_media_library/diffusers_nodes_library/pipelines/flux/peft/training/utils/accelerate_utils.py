from typing import Any

import diffusers  # type: ignore[reportMissingImports]
import torch  # type: ignore[reportMissingImports]
import torch.nn  # type: ignore[reportMissingImports]
from accelerate import Accelerator  # type: ignore[reportMissingImports]
from accelerate.logging import get_logger  # type: ignore[reportMissingImports]
from diffusers.utils import convert_unet_state_dict_to_peft  # type: ignore[reportPrivateImportUsage]
from diffusers.utils.torch_utils import is_compiled_module  # type: ignore[reportMissingImports]
from peft import get_peft_model_state_dict, set_peft_model_state_dict  # type: ignore[reportMissingImports]

logger = get_logger(__name__)


def unwrap_model(accelerator: Accelerator, model: torch.nn.Module) -> torch.nn.Module:
    """Unwraps the model from the accelerator, handling both compiled and non-compiled models."""
    model = accelerator.unwrap_model(model)
    model = model._orig_mod if is_compiled_module(model) else model  # type: ignore[reportAssignmentType]
    return model


def register_save_load_hooks(  # noqa: C901
    accelerator: Accelerator,
    transformer: torch.nn.Module,
) -> None:
    """Register custom save and load hooks for the transformer model in the Flux pipeline."""

    # create custom saving & loading hooks so that `accelerator.save_state(...)` serializes in a nice format
    def save_model_hook(models: Any, weights: Any, output_dir: str) -> None:
        if accelerator.is_main_process:
            transformer_lora_layers_to_save = None

            for model in models:
                if isinstance(model, type(unwrap_model(accelerator, transformer))):
                    transformer_lora_layers_to_save = get_peft_model_state_dict(model)
                else:
                    msg = f"unexpected save model: {model.__class__}"
                    raise TypeError(msg)

                # make sure to pop weight so that corresponding model is not saved again
                weights.pop()

            diffusers.FluxPipeline.save_lora_weights(  # type: ignore[reportPrivateImportUsage]
                output_dir,
                transformer_lora_layers=transformer_lora_layers_to_save,  # type: ignore[reportArgumentType]
            )

    def load_model_hook(models: Any, input_dir: str) -> None:
        transformer_ = None

        while len(models) > 0:
            model = models.pop()

            if isinstance(model, type(unwrap_model(accelerator, transformer))):
                transformer_ = model
            else:
                msg = f"unexpected save model: {model.__class__}"
                raise TypeError(msg)

        lora_state_dict = diffusers.FluxPipeline.lora_state_dict(input_dir)  # type: ignore[reportPrivateImportUsage]

        if not isinstance(lora_state_dict, dict):
            msg = (
                f"lora_state_dict should be a dict, but got {type(lora_state_dict)}. "
                f"Make sure to call `save_lora_weights` before loading."
            )
            raise TypeError(msg)

        transformer_state_dict = {
            f"{k.replace('transformer.', '')}": v for k, v in lora_state_dict.items() if k.startswith("transformer.")
        }
        transformer_state_dict = convert_unet_state_dict_to_peft(transformer_state_dict)
        incompatible_keys = set_peft_model_state_dict(transformer_, transformer_state_dict, adapter_name="default")
        if incompatible_keys is not None:
            # check only for unexpected keys
            unexpected_keys = getattr(incompatible_keys, "unexpected_keys", None)
            if unexpected_keys:
                logger.warning(
                    "Loading adapter weights from state_dict led to unexpected keys not found in the model: %s.",
                    unexpected_keys,
                )

    accelerator.register_save_state_pre_hook(save_model_hook)
    accelerator.register_load_state_pre_hook(load_model_hook)
