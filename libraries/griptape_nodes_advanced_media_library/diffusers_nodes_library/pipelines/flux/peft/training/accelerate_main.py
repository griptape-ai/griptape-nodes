import argparse
import copy
from accelerate import Accelerator
from accelerate.logging import get_logger
from accelerate.utils import DistributedDataParallelKwargs, ProjectConfiguration, set_seed
from pathlib import Path
import diffusers
import torch
from transformers import CLIPTokenizer, CLIPTextModel, CLIPTextModel, PretrainedConfig, T5TokenizerFast  # type: ignore[reportPrivateImportUsage]
from diffusers import (
    AutoencoderKL,  # type: ignore[reportPrivateImportUsage]
    FlowMatchEulerDiscreteScheduler,  # type: ignore[reportPrivateImportUsage]
    FluxTransformer2DModel,  # type: ignore[reportPrivateImportUsage]
)

from diffusers_nodes_library.pipelines.flux.peft.training.accelerate_parse_args import parse_args
from diffusers_nodes_library.pipelines.flux.peft.training.utils.logging import configure_logging
from diffusers_nodes_library.pipelines.flux.peft.training.utils.accelerate_utils import register_save_load_hooks, unwrap_model
from diffusers_nodes_library.pipelines.flux.peft.training.utils.seed import configure_seed
from peft import LoraConfig, set_peft_model_state_dict
from peft.utils import get_peft_model_state_dict

from diffusers_nodes_library.pipelines.flux.peft.training.utils.dreambooth_dataset import DreamBoothDataset, collate_fn
from diffusers_nodes_library.pipelines.flux.peft.training.utils.optimizer import create_optimizer
from tqdm.auto import tqdm

from diffusers_nodes_library.pipelines.flux.peft.training.utils.encode_prompt import encode_prompt


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
import copy
import itertools
import math
import os
import shutil
from pathlib import Path

import torch
from accelerate import Accelerator
from accelerate.logging import get_logger
from accelerate.utils import DistributedDataParallelKwargs, ProjectConfiguration
from peft import LoraConfig
from peft.utils import get_peft_model_state_dict
from diffusers.optimization import get_scheduler
from diffusers.training_utils import (
    compute_density_for_timestep_sampling,
    compute_loss_weighting_for_sd3,
    free_memory,
)




logger = get_logger(__name__)

def get_device_and_dtype(accelerator: Accelerator) -> tuple[torch.device, torch.dtype]:
    # TODO: Is it reallly necessary to use a specific dtype?
    #       On MPS -- mixed_precision="no" + dtype=torch.bfloat16 seems to work :shrug:
    #       We'll see what happens when we get to CUDA.
    #
    # logger.info("Copying the model to device with mixed_precision type (defaults to f32).")
    # # For mixed precision training we cast all non-trainable weights (vae, text_encoder and transformer) to half-precision
    # # as these weights are only used for inference, keeping weights in full precision is not required.
    # weight_dtype = torch.float32
    # if accelerator.mixed_precision == "fp16":
    #     weight_dtype = torch.bfloat16
    # elif accelerator.mixed_precision == "bf16":
    #     weight_dtype = torch.bfloat16
    # logger.info("Going to use bf16 ANYWAY.")
    # weight_dtype = torch.bfloat16

    return accelerator.device, torch.bfloat16


def main(args: argparse.Namespace) -> None:
    logging_dir = Path(args.output_dir, args.logging_dir)
    accelerator_project_config = ProjectConfiguration(project_dir=args.output_dir, logging_dir=str(logging_dir))
    kwargs = DistributedDataParallelKwargs(find_unused_parameters=True)
    accelerator = Accelerator(
        gradient_accumulation_steps=args.gradient_accumulation_steps,
        mixed_precision=args.mixed_precision,
        project_config=accelerator_project_config,
        kwargs_handlers=[kwargs],
    )

    # TODO: DO WE NEED THIS?
    # # Disable AMP for MPS.
    # logger.info(f"Disabling AMP if MPS.")
    # if torch.backends.mps.is_available():
    #     accelerator.native_amp = False

    configure_logging(accelerator, logger)
    configure_seed(args.seed)
    device, dtype = get_device_and_dtype(accelerator)

    # TODO: Seems like we are loading all of the components provided by FluxPipeline.... Why not load the pipeline directly?

    # Load the tokenizers
    logger.info("Loading tokenizer.")
    tokenizer_one = CLIPTokenizer.from_pretrained(
        args.pretrained_model_name_or_path,
        subfolder="tokenizer",
        revision=args.revision,
        torch_dtype=dtype,
    )

    logger.info("Loading tokenizer_2.")
    tokenizer_two = T5TokenizerFast.from_pretrained(
        args.pretrained_model_name_or_path,
        subfolder="tokenizer_2",
        revision=args.revision,
        torch_dtype=dtype,
    )

    logger.info("Loading text encoder.")
    text_encoder_one = CLIPTextModel.from_pretrained(
        args.pretrained_model_name_or_path,
        subfolder="text_encoder",
        revision=args.revision,
        torch_dtype=dtype,
    )

    logger.info("Loading text encoder_2.")
    text_encoder_two = CLIPTextModel.from_pretrained(
        args.pretrained_model_name_or_path,
        subfolder="text_encoder_2",
        revision=args.revision,
        torch_dtype=dtype,
    )

    logger.info("Loading scheduler.")
    noise_scheduler = FlowMatchEulerDiscreteScheduler.from_pretrained(
        args.pretrained_model_name_or_path, subfolder="scheduler"
    )

    logger.info("Copying noise scheduler.")
    noise_scheduler_copy = copy.deepcopy(noise_scheduler)

    logger.info("Loading vae.")
    vae = AutoencoderKL.from_pretrained(
        args.pretrained_model_name_or_path,
        subfolder="vae",
        revision=args.revision,
        variant=args.variant,
        torch_dtype=dtype,
    )

    logger.info("Loading transformer.")
    transformer = FluxTransformer2DModel.from_pretrained(
        args.pretrained_model_name_or_path,
        subfolder="transformer",
        revision=args.revision,
        variant=args.variant,
        torch_dtype=dtype,
    )


    # Freeze the base model parameters.
    # We only want to train the LoRA parameters.
    logger.info("Freezing the base model parameters.")
    transformer.requires_grad_(False)
    vae.requires_grad_(False)
    text_encoder_one.requires_grad_(False)
    text_encoder_two.requires_grad_(False)

    logger.info(f"Copying vae to accelerator device -- {device} {dtype}.")
    # TODO: Why can't I do xxx.to(device, dtype)? Why do I need to use accelerator.device?
    vae.to(accelerator.device, dtype=dtype)
    transformer.to(accelerator.device, dtype=dtype)
    text_encoder_one.to(accelerator.device, dtype=dtype)
    text_encoder_two.to(accelerator.device, dtype=dtype)


    # TODO: Gradient checkpointing is supposed to help with memory usage.
    #       So I might need this, but let's see how it goes without it.
    # logger.info("Enabling gradient checkpointing if required.")
    # if args.gradient_checkpointing:
    #     transformer.enable_gradient_checkpointing()

    # TODO: expose target modules...maybe or... maybe only if someone screams.
    # TODO: I saw some awesome doc or code or something that talked about typical layers sets
    #       used by other lora training frameworks like ostris nad flux gym... where was that?
    # if args.lora_layers is not None:
    #     target_modules = [layer.strip() for layer in args.lora_layers.split(",")]
    # else:
    target_modules = [
        "attn.to_k",
        "attn.to_q",
        "attn.to_v",
        "attn.to_out.0",
        "attn.add_k_proj",
        "attn.add_q_proj",
        "attn.add_v_proj",
        "attn.to_add_out",
        "ff.net.0.proj",
        "ff.net.2",
        "ff_context.net.0.proj",
        "ff_context.net.2",
    ]

    # now we will add new LoRA weights the transformer layers
    logger.info("Creating lora config and adding as adapter to transformer.")
    transformer_lora_config = LoraConfig(
        r=args.rank,
        lora_alpha=args.rank,
        lora_dropout=args.lora_dropout,
        init_lora_weights="gaussian",
        target_modules=target_modules,
    )
    transformer.add_adapter(transformer_lora_config)

    logger.info("Registering save and load model hooks with accelerator.")
    register_save_load_hooks(accelerator, transformer)


    # TODO: as needed
    # # Enable TF32 for faster training on Ampere GPUs,
    # # cf https://pytorch.org/docs/stable/notes/cuda.html#tensorfloat-32-tf32-on-ampere-devices
    # if args.allow_tf32 and torch.cuda.is_available():
    #     torch.backends.cuda.matmul.allow_tf32 = True


    # DO I actually want to do this?
    # Probably not -- who's going to understand -- why??
    # if args.scale_lr:
    #     args.learning_rate = (
    #         args.learning_rate * args.gradient_accumulation_steps * args.train_batch_size * accelerator.num_processes
    #     )


    # TODO: Do I really need to do this -- LETS FIND OUT!
    # # Make sure the trainable params are in float32.
    # logger.info("Cast trainable parameters to float32 if using mixed precision of fp16.")
    # if args.mixed_precision == "fp16":
    #     models = [transformer]
    #     if args.train_text_encoder:
    #         models.extend([text_encoder_one])
    #     # only upcast trainable parameters (LoRA) into fp32
    #     cast_training_params(models, dtype=torch.float32)


    # Optimization parameters
    transformer_lora_parameters = list(filter(lambda p: p.requires_grad, transformer.parameters()))
    transformer_parameters_with_lr = {"params": transformer_lora_parameters, "lr": args.learning_rate}
    params_to_optimize = [transformer_parameters_with_lr]


    logger.info("Creating optimizer.")
    optimizer = create_optimizer(args, params_to_optimize)

    # Dataset and DataLoaders creation:
    logger.info("Loading dreambooth dataset.")
    train_dataset = DreamBoothDataset(
        instance_data_root=args.instance_data_dir,
        instance_prompt=args.instance_prompt,
        class_prompt=args.class_prompt,
        class_data_root=args.class_data_dir if args.with_prior_preservation else None,
        class_num=args.num_class_images,
        size=args.resolution,
        repeats=args.repeats,
        center_crop=args.center_crop,
        dataset_name=args.dataset_name,
        dataset_config_name=args.dataset_config_name,
        cache_dir=args.cache_dir,
        image_column=args.image_column,
        caption_column=args.caption_column,
        random_flip=args.random_flip,
        resolution=args.resolution,
    )

    logger.info("Creating data loader.")
    train_dataloader = torch.utils.data.DataLoader(
        train_dataset,
        batch_size=args.train_batch_size,
        shuffle=True,
        collate_fn=lambda examples: collate_fn(examples, args.with_prior_preservation),
        num_workers=args.dataloader_num_workers,
    )

    ################################################################
    # TODO: REFACTOR A START
    ################################################################

    tokenizers = [tokenizer_one, tokenizer_two]
    text_encoders = [text_encoder_one, text_encoder_two]

    def compute_text_embeddings(prompt, text_encoders, tokenizers):
        with torch.no_grad():
            prompt_embeds, pooled_prompt_embeds, text_ids = encode_prompt(
                text_encoders, tokenizers, prompt, args.max_sequence_length
            )
            prompt_embeds = prompt_embeds.to(accelerator.device)
            pooled_prompt_embeds = pooled_prompt_embeds.to(accelerator.device)
            text_ids = text_ids.to(accelerator.device)
        return prompt_embeds, pooled_prompt_embeds, text_ids

    # If custom instance prompts are NOT
    # provided (i.e. the --instance_prompt is used for all images), we encode the instance prompt once to avoid
    # the redundant encoding.
    if not train_dataset.custom_instance_prompts:
        instance_prompt_hidden_states, instance_pooled_prompt_embeds, instance_text_ids = compute_text_embeddings(
            args.instance_prompt, text_encoders, tokenizers
        )

    # Handle class prompt for prior-preservation.
    if args.with_prior_preservation:
        if not args.train_text_encoder:
            class_prompt_hidden_states, class_pooled_prompt_embeds, class_text_ids = compute_text_embeddings(
                args.class_prompt, text_encoders, tokenizers
            )

    # Clear the memory here
    if not train_dataset.custom_instance_prompts:
        del text_encoder_one, text_encoder_two, tokenizer_one, tokenizer_two
        free_memory()

        # If custom instance prompts are NOT provided (i.e. the instance prompt is used for all images),
    # pack the statically computed variables appropriately here. This is so that we don't
    # have to pass them to the dataloader.

    if not train_dataset.custom_instance_prompts:
        prompt_embeds = instance_prompt_hidden_states  # type: ignore
        pooled_prompt_embeds = instance_pooled_prompt_embeds  # type: ignore
        text_ids = instance_text_ids  # type: ignore
        if args.with_prior_preservation:
            prompt_embeds = torch.cat([prompt_embeds, class_prompt_hidden_states], dim=0)  # type: ignore
            pooled_prompt_embeds = torch.cat([pooled_prompt_embeds, class_pooled_prompt_embeds], dim=0)  # type: ignore
            text_ids = torch.cat([text_ids, class_text_ids], dim=0)  # type: ignore


    # TODO: These are used in the training loop... seems like wrong level of detail here...``
    vae_config_shift_factor = vae.config.shift_factor  # type: ignore
    vae_config_scaling_factor = vae.config.scaling_factor  # type: ignore
    vae_config_block_out_channels = vae.config.block_out_channels  # type: ignore


    logger.info("Caching latents if enabled.")
    if args.cache_latents:
        logger.info("Caching latents.")
        latents_cache = []
        for batch in tqdm(train_dataloader, desc="Caching latents"):
            with torch.no_grad():
                batch["pixel_values"] = batch["pixel_values"].to(
                    accelerator.device, non_blocking=True, dtype=dtype
                )
                latents_cache.append(vae.encode(batch["pixel_values"]).latent_dist)  # type: ignore

        if args.validation_prompt is None:
            del vae
            free_memory()

    # Scheduler and math around the number of training steps.
    # Check the PR https://github.com/huggingface/diffusers/pull/8312 for detailed explanation.
    num_warmup_steps_for_scheduler = args.lr_warmup_steps * accelerator.num_processes
    # if args.max_train_steps is None:
    #     len_train_dataloader_after_sharding = math.ceil(len(train_dataloader) / accelerator.num_processes)
    #     num_update_steps_per_epoch = math.ceil(len_train_dataloader_after_sharding / args.gradient_accumulation_steps)
    #     num_training_steps_for_scheduler = (
    #         args.num_train_epochs * accelerator.num_processes * num_update_steps_per_epoch
    #     )
    # else:
    num_training_steps_for_scheduler = args.max_train_steps * accelerator.num_processes

    logger.info("Getting scheduler.")
    lr_scheduler = get_scheduler(
        args.lr_scheduler,
        optimizer=optimizer,
        num_warmup_steps=num_warmup_steps_for_scheduler,
        num_training_steps=num_training_steps_for_scheduler,
        num_cycles=args.lr_num_cycles,
        power=args.lr_power,
    )

    # Prepare everything with our `accelerator`.
    transformer, optimizer, train_dataloader, lr_scheduler = accelerator.prepare(
        transformer, optimizer, train_dataloader, lr_scheduler
    )
        

    # We need to recalculate our total training steps as the size of the training dataloader may have changed.
    num_update_steps_per_epoch = math.ceil(len(train_dataloader) / args.gradient_accumulation_steps)
    # if args.max_train_steps is None:
    #     args.max_train_steps = args.num_train_epochs * num_update_steps_per_epoch
    #     if num_training_steps_for_scheduler != args.max_train_steps:
    #         logger.warning(
    #             f"The length of the 'train_dataloader' after 'accelerator.prepare' ({len(train_dataloader)}) does not match "
    #             f"the expected length ({len_train_dataloader_after_sharding}) when the learning rate scheduler was created. "
    #             f"This inconsistency may result in the learning rate scheduler not functioning properly."
    #         )
    # Afterwards we recalculate our number of training epochs
    args.num_train_epochs = math.ceil(args.max_train_steps / num_update_steps_per_epoch)

    logger.info("Initing trackers if main process.")
    # We need to initialize the trackers we use, and also store our configuration.
    # The trackers initializes automatically on the main process.
    if accelerator.is_main_process:
        tracker_name = "dreambooth-flux-dev-lora"
        accelerator.init_trackers(tracker_name, config=vars(args))

    # Train!
    total_batch_size = args.train_batch_size * accelerator.num_processes * args.gradient_accumulation_steps

    logger.info("***** Running training *****")
    logger.info(f"  Num examples = {len(train_dataset)}")
    logger.info(f"  Num batches each epoch = {len(train_dataloader)}")
    logger.info(f"  Num Epochs = {args.num_train_epochs}")
    logger.info(f"  Instantaneous batch size per device = {args.train_batch_size}")
    logger.info(f"  Total train batch size (w. parallel, distributed & accumulation) = {total_batch_size}")
    logger.info(f"  Gradient Accumulation steps = {args.gradient_accumulation_steps}")
    logger.info(f"  Total optimization steps = {args.max_train_steps}")
    global_step = 0
    first_epoch = 0

    # Potentially load in the weights and states from a previous save
    logger.info(f"  Resume from checkpoint {args.resume_from_checkpoint}")
    if args.resume_from_checkpoint:
        if args.resume_from_checkpoint != "latest":
            path = os.path.basename(args.resume_from_checkpoint)
        else:
            # Get the mos recent checkpoint
            dirs = os.listdir(args.output_dir)
            dirs = [d for d in dirs if d.startswith("checkpoint")]
            dirs = sorted(dirs, key=lambda x: int(x.split("-")[1]))
            path = dirs[-1] if len(dirs) > 0 else None

        if path is None:
            accelerator.print(
                f"Checkpoint '{args.resume_from_checkpoint}' does not exist. Starting a new training run."
            )
            args.resume_from_checkpoint = None
            initial_global_step = 0
        else:
            accelerator.print(f"Resuming from checkpoint {path}")
            accelerator.load_state(os.path.join(args.output_dir, path))
            global_step = int(path.split("-")[1])

            initial_global_step = global_step
            first_epoch = global_step // num_update_steps_per_epoch

    else:
        initial_global_step = 0

    progress_bar = tqdm(
        range(0, args.max_train_steps),
        initial=initial_global_step,
        desc="Steps",
        # Only show the progress bar once on each machine.
        disable=not accelerator.is_local_main_process,
    )

    def get_sigmas(timesteps, n_dim=4, dtype=torch.float32):
        sigmas = noise_scheduler_copy.sigmas.to(device=accelerator.device, dtype=dtype)  # type: ignore
        schedule_timesteps = noise_scheduler_copy.timesteps.to(accelerator.device)  # type: ignore
        timesteps = timesteps.to(accelerator.device)
        step_indices = [(schedule_timesteps == t).nonzero().item() for t in timesteps]

        sigma = sigmas[step_indices].flatten()
        while len(sigma.shape) < n_dim:
            sigma = sigma.unsqueeze(-1)
        return sigma


    ################################################################
    # TODO: REFACTOR A END
    ################################################################
    logger.info("Starting training")
    for epoch in range(first_epoch, args.num_train_epochs):
        logger.info(f"Epoch {epoch + 1}/{args.num_train_epochs}")

        transformer.train()

        for step, batch in enumerate(train_dataloader):
            logger.debug(f"Step {step}/{len(train_dataloader)}")
            models_to_accumulate = [transformer]
            with accelerator.accumulate(models_to_accumulate):
                prompts = batch["prompts"]

                # encode batch prompts when custom prompts are provided for each image -
                if train_dataset.custom_instance_prompts:
                    prompt_embeds, pooled_prompt_embeds, text_ids = compute_text_embeddings(
                        prompts, text_encoders, tokenizers
                    )
                else:
                    elems_to_repeat = len(prompts)
                    if args.train_text_encoder:
                        prompt_embeds, pooled_prompt_embeds, text_ids = encode_prompt(
                            text_encoders=[text_encoder_one, text_encoder_two],  # type: ignore
                            tokenizers=[None, None],  # type: ignore
                            text_input_ids_list=[
                                tokens_one.repeat(elems_to_repeat, 1),  # type: ignore
                                tokens_two.repeat(elems_to_repeat, 1),  # type: ignore
                            ],
                            max_sequence_length=args.max_sequence_length,
                            device=accelerator.device,
                            prompt=args.instance_prompt,
                        )

                # Convert images to latent space
                if args.cache_latents:
                    model_input = latents_cache[step].sample()  # type: ignore
                else:
                    pixel_values = batch["pixel_values"].to(dtype=vae.dtype)  # type: ignore
                    model_input = vae.encode(pixel_values).latent_dist.sample()  # type: ignore
                model_input = (model_input - vae_config_shift_factor) * vae_config_scaling_factor
                model_input = model_input.to(dtype=dtype)  # type: ignore

                vae_scale_factor = 2 ** (len(vae_config_block_out_channels) - 1)

                latent_image_ids = diffusers.FluxPipeline._prepare_latent_image_ids(  # type: ignore
                    model_input.shape[0],
                    model_input.shape[2] // 2,
                    model_input.shape[3] // 2,
                    accelerator.device,
                    dtype,
                )
                # Sample noise that we'll add to the latents
                noise = torch.randn_like(model_input)
                bsz = model_input.shape[0]

                # Sample a random timestep for each image
                # for weighting schemes where we sample timesteps non-uniformly
                u = compute_density_for_timestep_sampling(
                    weighting_scheme=args.weighting_scheme,
                    batch_size=bsz,
                    logit_mean=args.logit_mean,
                    logit_std=args.logit_std,
                    mode_scale=args.mode_scale,
                )
                indices = (u * noise_scheduler_copy.config.num_train_timesteps).long()  # type: ignore
                timesteps = noise_scheduler_copy.timesteps[indices].to(device=model_input.device)  # type: ignore

                # Add noise according to flow matching.
                # zt = (1 - texp) * x + texp * z1
                sigmas = get_sigmas(timesteps, n_dim=model_input.ndim, dtype=model_input.dtype)
                noisy_model_input = (1.0 - sigmas) * model_input + sigmas * noise

                packed_noisy_model_input = diffusers.FluxPipeline._pack_latents(  # type: ignore
                    noisy_model_input,
                    batch_size=model_input.shape[0],
                    num_channels_latents=model_input.shape[1],
                    height=model_input.shape[2],
                    width=model_input.shape[3],
                )

                # handle guidance
                if unwrap_model(accelerator, transformer).config.guidance_embeds:  # type: ignore
                    guidance = torch.tensor([args.guidance_scale], device=accelerator.device)
                    guidance = guidance.expand(model_input.shape[0])
                else:
                    guidance = None

                # Predict the noise residual
                model_pred = transformer(
                    hidden_states=packed_noisy_model_input,
                    # YiYi notes: divide it by 1000 for now because we scale it by 1000 in the transformer model (we should not keep it but I want to keep the inputs same for the model for testing)
                    timestep=timesteps / 1000,
                    guidance=guidance,
                    pooled_projections=pooled_prompt_embeds,  # type: ignore
                    encoder_hidden_states=prompt_embeds,  # type: ignore
                    txt_ids=text_ids,  # type: ignore
                    img_ids=latent_image_ids,
                    return_dict=False,
                )[0]
                model_pred = diffusers.FluxPipeline._unpack_latents(  # type: ignore
                    model_pred,
                    height=model_input.shape[2] * vae_scale_factor,
                    width=model_input.shape[3] * vae_scale_factor,
                    vae_scale_factor=vae_scale_factor,
                )

                # these weighting schemes use a uniform timestep sampling
                # and instead post-weight the loss
                weighting = compute_loss_weighting_for_sd3(weighting_scheme=args.weighting_scheme, sigmas=sigmas)

                # flow matching loss
                target = noise - model_input

                if args.with_prior_preservation:
                    # Chunk the noise and model_pred into two parts and compute the loss on each part separately.
                    model_pred, model_pred_prior = torch.chunk(model_pred, 2, dim=0)
                    target, target_prior = torch.chunk(target, 2, dim=0)

                    # Compute prior loss
                    prior_loss = torch.mean(
                        (weighting.float() * (model_pred_prior.float() - target_prior.float()) ** 2).reshape(
                            target_prior.shape[0], -1
                        ),
                        1,
                    )
                    prior_loss = prior_loss.mean()

                # Compute regular loss.
                loss = torch.mean(
                    (weighting.float() * (model_pred.float() - target.float()) ** 2).reshape(target.shape[0], -1),
                    1,
                )
                loss = loss.mean()

                if args.with_prior_preservation:
                    # Add the prior loss to the instance loss.
                    loss = loss + args.prior_loss_weight * prior_loss  # type: ignore

                accelerator.backward(loss)
                if accelerator.sync_gradients:
                    params_to_clip = (
                        itertools.chain(transformer.parameters(), text_encoder_one.parameters())  # type: ignore
                        if args.train_text_encoder
                        else transformer.parameters()
                    )
                    accelerator.clip_grad_norm_(params_to_clip, args.max_grad_norm)

                optimizer.step()
                lr_scheduler.step()
                optimizer.zero_grad()

            # Checks if the accelerator has performed an optimization step behind the scenes
            if accelerator.sync_gradients:
                progress_bar.update(1)
                global_step += 1

                if accelerator.is_main_process:
                    if global_step % args.checkpointing_steps == 0:
                        # _before_ saving state, check if this save would set us over the `checkpoints_total_limit`
                        if args.checkpoints_total_limit is not None:
                            checkpoints = os.listdir(args.output_dir)
                            checkpoints = [d for d in checkpoints if d.startswith("checkpoint")]
                            checkpoints = sorted(checkpoints, key=lambda x: int(x.split("-")[1]))

                            # before we save the new checkpoint, we need to have at _most_ `checkpoints_total_limit - 1` checkpoints
                            if len(checkpoints) >= args.checkpoints_total_limit:
                                num_to_remove = len(checkpoints) - args.checkpoints_total_limit + 1
                                removing_checkpoints = checkpoints[0:num_to_remove]

                                logger.info(
                                    f"{len(checkpoints)} checkpoints already exist, removing {len(removing_checkpoints)} checkpoints"
                                )
                                logger.info(f"removing checkpoints: {', '.join(removing_checkpoints)}")

                                for removing_checkpoint in removing_checkpoints:
                                    removing_checkpoint = os.path.join(args.output_dir, removing_checkpoint)
                                    shutil.rmtree(removing_checkpoint)

                        save_path = os.path.join(args.output_dir, f"checkpoint-{global_step}")
                        accelerator.save_state(save_path)
                        logger.info(f"Saved state to {save_path}")

            logs = {"loss": loss.detach().item(), "lr": lr_scheduler.get_last_lr()[0]}
            progress_bar.set_postfix(**logs)
            accelerator.log(logs, step=global_step)

            if global_step >= args.max_train_steps:
                break

        # if accelerator.is_main_process:
        #     if args.validation_prompt is not None and epoch % args.validation_epochs == 0:
        #         # create pipeline
        #         if not args.train_text_encoder:
        #             text_encoder_one, text_encoder_two = load_text_encoders(text_encoder_cls_one, text_encoder_cls_two)
        #             text_encoder_one.to(dtype)
        #             text_encoder_two.to(dtype)
        #         pipeline = diffusers.FluxPipeline.from_pretrained(
        #             args.pretrained_model_name_or_path,
        #             vae=vae,
        #             text_encoder=unwrap_model(text_encoder_one),
        #             text_encoder_2=unwrap_model(text_encoder_two),
        #             transformer=unwrap_model(transformer),
        #             revision=args.revision,
        #             variant=args.variant,
        #             torch_dtype=weight_dtype,
        #         )
        #         pipeline_args = {"prompt": args.validation_prompt}
        #         images = log_validation(
        #             pipeline=pipeline,
        #             args=args,
        #             accelerator=accelerator,
        #             pipeline_args=pipeline_args,
        #             epoch=epoch,
        #             torch_dtype=weight_dtype,
        #             is_final_validation=True, #???
        #             suffix=f"_wip",
        #         )
        #         if not args.train_text_encoder:
        #             del text_encoder_one, text_encoder_two
        #             free_memory()

        #         images = None
        #         del pipeline

    # Save the lora layers
    logger.info("Saving the LoRA weights")
    accelerator.wait_for_everyone()
    if accelerator.is_main_process:
        transformer = unwrap_model(accelerator, transformer)
        if args.upcast_before_saving:
            transformer.to(torch.float32)
        else:
            transformer = transformer.to(dtype)

        diffusers.FluxPipeline.save_lora_weights(  # type: ignore
            save_directory=args.output_dir,
            transformer_lora_layers=get_peft_model_state_dict(transformer),
        )


        # FREE ALL THE THINGS?
        logger.info("Freeing all the things")
        del transformer
        del train_dataset
        del train_dataloader
        del optimizer
        del lr_scheduler
        del noise_scheduler_copy
        free_memory()

        # logger.info("Final inference")

        # # Final inference
        # # Load previous pipeline
        # pipeline = diffusers.FluxPipeline.from_pretrained(  # type: ignore
        #     args.pretrained_model_name_or_path,
        #     revision=args.revision,
        #     variant=args.variant,
        #     torch_dtype=dtype,
        # )

        # # run inference
        # images = []
        # if args.validation_prompt and args.num_validation_images > 0:
        #     pipeline_args = {"prompt": args.validation_prompt}
        #     # logger.info("Gen images without lora")
        #     # images = log_validation(
        #     #     pipeline=pipeline,
        #     #     args=args,
        #     #     accelerator=accelerator,
        #     #     pipeline_args=pipeline_args,
        #     #     epoch=epoch,
        #     #     is_final_validation=True,
        #     #     torch_dtype=weight_dtype,
        #     #     suffix="_without_lora",
        #     # )
        #     pipeline.load_lora_weights(args.output_dir)
        #     logger.info("Gen images with lora")
        #     images = log_validation(
        #         pipeline=pipeline,
        #         args=args,
        #         accelerator=accelerator,
        #         pipeline_args=pipeline_args,
        #         epoch=epoch,  # type: ignore
        #         is_final_validation=True,
        #         torch_dtype=dtype,
        #         suffix="_final_with_lora",
        #     )

        # images = None
        # del pipeline

    accelerator.end_training()


if __name__ == "__main__":
    args = parse_args()
    main(args)
