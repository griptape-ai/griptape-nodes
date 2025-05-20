#!/usr/bin/env python
# coding=utf-8
# Copyright 2025 The HuggingFace Inc. team. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and

import argparse

import torch
from accelerate import Accelerator
from accelerate.logging import get_logger
from peft import  set_peft_model_state_dict
from peft.utils import get_peft_model_state_dict

import diffusers
from diffusers.utils import convert_unet_state_dict_to_peft  # type: ignore[reportPrivateImportUsage]
from diffusers.utils.hub_utils import load_or_create_model_card, populate_model_card


from accelerate import Accelerator

from diffusers.utils.torch_utils import is_compiled_module

from peft import get_peft_model_state_dict
import torch.nn
import diffusers


logger = get_logger(__name__)

def unwrap_model(accelerator: Accelerator, model: torch.nn.Module) -> torch.nn.Module:
        model = accelerator.unwrap_model(model)
        model = model._orig_mod if is_compiled_module(model) else model  # type: ignore
        return model


def register_save_load_hooks(
    accelerator: Accelerator,
    transformer: torch.nn.Module,
):
    # create custom saving & loading hooks so that `accelerator.save_state(...)` serializes in a nice format
    def save_model_hook(models, weights, output_dir):
        if accelerator.is_main_process:
            transformer_lora_layers_to_save = None

            for model in models:
                if isinstance(model, type(unwrap_model(accelerator, transformer))):
                    transformer_lora_layers_to_save = get_peft_model_state_dict(model)
                else:
                    raise ValueError(f"unexpected save model: {model.__class__}")

                # make sure to pop weight so that corresponding model is not saved again
                weights.pop()

            diffusers.FluxPipeline.save_lora_weights(  # type: ignore[reportPrivateImportUsage]
                output_dir,
                transformer_lora_layers=transformer_lora_layers_to_save,  # type: ignore[reportArgumentType]
            )

    def load_model_hook(models, input_dir):
        transformer_ = None

        while len(models) > 0:
            model = models.pop()

            if isinstance(model, type(unwrap_model(accelerator, transformer))):
                transformer_ = model
            else:
                raise ValueError(f"unexpected save model: {model.__class__}")

        lora_state_dict = diffusers.FluxPipeline.lora_state_dict(input_dir)  # type: ignore[reportPrivateImportUsage]

        if not isinstance(lora_state_dict, dict):
            raise ValueError(
                f"lora_state_dict should be a dict, but got {type(lora_state_dict)}. "
                f"Make sure to call `save_lora_weights` before loading."
            )

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
                    f"Loading adapter weights from state_dict led to unexpected keys not found in the model: "
                    f" {unexpected_keys}. "
                )

        # TODO: Verify this is ACTUALLY STILL needed -- I'm not using fp16 yet anyway.
        # # Make sure the trainable params are in float32. This is again needed since the base models
        # # are in `weight_dtype`. More details:
        # # https://github.com/huggingface/diffusers/pull/6514#discussion_r1449796804
        # if args.mixed_precision == "fp16":
        #     models = [transformer_]
        #     # only upcast trainable parameters (LoRA) into fp32
        #     cast_training_params(models)


    accelerator.register_save_state_pre_hook(save_model_hook)
    accelerator.register_load_state_pre_hook(load_model_hook)