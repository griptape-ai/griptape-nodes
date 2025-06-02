import argparse
import copy
import math
import shutil
from contextlib import nullcontext
from pathlib import Path
from typing import Any

import diffusers  # type: ignore[reportMissingImports]
import torch  # type: ignore[reportMissingImports]
from accelerate import Accelerator  # type: ignore[reportMissingImports]
from accelerate.logging import get_logger  # type: ignore[reportMissingImports]
from accelerate.utils import (  # type: ignore[reportMissingImports]
    DistributedDataParallelKwargs,
    ProjectConfiguration,
    set_seed,
)
from accelerate_parse_args import parse_args
from diffusers import (  # type: ignore[reportMissingImports]
    AutoencoderKL,  # type: ignore[reportPrivateImportUsage]
    FlowMatchEulerDiscreteScheduler,  # type: ignore[reportPrivateImportUsage]
    FluxTransformer2DModel,  # type: ignore[reportPrivateImportUsage]
)
from diffusers.optimization import get_scheduler  # type: ignore[reportMissingImports]
from diffusers.training_utils import (  # type: ignore[reportMissingImports]
    compute_density_for_timestep_sampling,
    compute_loss_weighting_for_sd3,
    free_memory,
)
from peft import LoraConfig  # type: ignore[reportAttributeAccessIssue]
from peft.utils import get_peft_model_state_dict  # type: ignore[reportMissingImports]
from PIL.Image import Image  # type: ignore[reportMissingImports]
from tqdm.auto import tqdm  # type: ignore[reportMissingImports]
from transformers import (  # type: ignore[reportMissingImports]
    CLIPTextModel,  # type: ignore[reportAttributeAccessIssue]
    CLIPTokenizer,  # type: ignore[reportAttributeAccessIssue]
    T5EncoderModel,  # type: ignore[reportAttributeAccessIssue]
    T5TokenizerFast,  # type: ignore[reportAttributeAccessIssue]
)
from utils.accelerate_utils import register_save_load_hooks, unwrap_model
from utils.dreambooth_dataset import DreamBoothDataset, collate_fn
from utils.encode_prompt import encode_prompt
from utils.logging import configure_logging
from utils.optimizer import create_optimizer

from diffusers_nodes_library.common.utils.torch_utils import (
    human_readable_memory_footprint,
    to_human_readable_size,
)
from diffusers_nodes_library.pipelines.flux.peft.training.utils.memory import (  # type: ignore[reportMissingImports]
    apply_cpu_offload_to_non_lora_modules,
    gpu_vram_profiling,
    lora_modules_to,
)

logger = get_logger(__name__)


class FluxLoraTrainingScript:
    def __init__(self, args: argparse.Namespace):
        self.args = args

        # All of these are set to None initially and will be configured in the order of the training script.
        # Sometimes they will be set back and forth to, for example, save memory.
        self.accelerator = None
        self.device = None
        self.mixed_precision = None
        self.frozen_dtype = None
        self.trainable_dtype = None
        self.tokenizer_one = None
        self.tokenizer_two = None
        self.text_encoder_one = None
        self.text_encoder_two = None
        self.vae = None
        self.vae_config_shift_factor = None
        self.vae_config_scaling_factor = None
        self.vae_config_block_out_channels = None

    def _configure_accelerator(self) -> None:
        args = self.args
        logging_dir = Path(args.output_dir, args.logging_dir)
        accelerator_project_config = ProjectConfiguration(project_dir=args.output_dir, logging_dir=str(logging_dir))
        kwargs = DistributedDataParallelKwargs(find_unused_parameters=True)
        self.accelerator = Accelerator(
            gradient_accumulation_steps=args.gradient_accumulation_steps,
            mixed_precision=args.mixed_precision,
            project_config=accelerator_project_config,
            kwargs_handlers=[kwargs],
        )
        configure_logging(self.accelerator, logger)

    def _configure_device(self) -> None:
        if self.accelerator is None:
            msg = "Accelerator must be configured before configuring device and dtype."
            raise RuntimeError(msg)

        # TODO: https://github.com/griptape-ai/griptape-nodes/issues/1354
        #       DO WE NEED THIS? WHY WAS THIS PRESENT IN EXAMPLE CODE? IS IT STILL RELEVANT AFTER MY CHANGES?
        # # Disable AMP for MPS.
        # logger.info(f"Disabling AMP if MPS.")  # noqa: ERA001
        # if torch.backends.mps.is_available():
        #     accelerator.native_amp = False  # noqa: ERA001

        # TODO: https://github.com/griptape-ai/griptape-nodes/issues/1354
        #       DO WE NEED THIS? IS IT STILL RELEVANT AFTER MY CHANGES?
        # # Enable TF32 for faster training on Ampere GPUs,
        # # cf https://pytorch.org/docs/stable/notes/cuda.html#tensorfloat-32-tf32-on-ampere-devices
        # if args.allow_tf32 and torch.cuda.is_available():
        #     torch.backends.cuda.matmul.allow_tf32 = True  # noqa: ERA001

        self.device = self.accelerator.device
        self.mixed_precision = self.accelerator.mixed_precision

        if self.mixed_precision != self.args.frozen_dtype:
            logger.warning(
                "Mixed precision (%s) does not match frozen dtype (%s). "
                "This may lead to unexpected behavior, but "
                "doesn't mean you can't or shouldn't do it (e.g. single mac with MPS).",
                self.mixed_precision,
                self.args.frozen_dtype,
            )

        match self.args.frozen_dtype:
            case "fp32":
                self.frozen_dtype = torch.float32
            case "fp16":
                self.frozen_dtype = torch.float16
            case "bf16":
                self.frozen_dtype = torch.bfloat16
            case _:
                msg = f"Unsupported frozen dtype: {self.args.frozen_dtype}. Supported values are 'fp32', 'fp16', or 'bf16'."
                raise ValueError(msg)

        # We are always using float32 for trainable parameters.
        # Not sure why, I got this from an example somewhere that said its was "important" shrug.
        self.trainable_dtype = torch.float32

        logger.info(
            "Using device: %s with mixed precision: %s, frozen dtype: %s, trainable dtype: %s.",
            self.device,
            self.mixed_precision,
            self.frozen_dtype,
            self.trainable_dtype,
        )

    def _set_seed(self) -> None:
        if args.seed is not None:
            logger.info("Seed provided, setting seed to %d.", args.seed)
            set_seed(args.seed)

    def _load_schedulers(self) -> None:
        if self.frozen_dtype is None:
            msg = "Frozen dtype must be configured before loading schedulers."
            raise RuntimeError(msg)

        logger.info("Loading scheduler.")
        self.noise_scheduler = FlowMatchEulerDiscreteScheduler.from_pretrained(
            args.pretrained_model_name_or_path,
            subfolder="scheduler",
            torch_dtype=self.frozen_dtype,
        )

        logger.info("Copying noise scheduler.")
        self.noise_scheduler_copy = copy.deepcopy(self.noise_scheduler)

    def _load_transformer(self) -> None:
        if self.frozen_dtype is None:
            msg = "Frozen dtype must be configured before loading schedulers."
            raise RuntimeError(msg)

        logger.info("Loading transformer.")
        self.transformer = FluxTransformer2DModel.from_pretrained(
            args.pretrained_model_name_or_path,
            subfolder="transformer",
            revision=args.revision,
            variant=args.variant,
            torch_dtype=self.frozen_dtype,
        )

        # Freeze the base model parameters.
        # We only want to train the LoRA parameters.
        logger.info("Freezing the base model parameters (including transformer, vae, text encoders).")
        self.transformer.requires_grad_(False)

    def _load_text_encoders(self) -> None:
        if self.text_encoder_one is not None:
            logger.info("text_encoder_one (clip) already loaded, skipping loading.")
        else:
            logger.info("Loading tokenizer.")
            self.tokenizer_one = CLIPTokenizer.from_pretrained(
                args.pretrained_model_name_or_path,
                subfolder="tokenizer",
                revision=args.revision,
                torch_dtype=self.frozen_dtype,
            )

            logger.info("Loading text_encoder_one with %s", self.frozen_dtype)
            self.text_encoder_one = CLIPTextModel.from_pretrained(
                args.pretrained_model_name_or_path,
                subfolder="text_encoder",
                revision=args.revision,
                torch_dtype=self.frozen_dtype,
            )

            logger.info("Freezing text_encoder_one parameters.")
            self.text_encoder_one.requires_grad_(False)

        if self.text_encoder_two is not None:
            logger.info("text_encoder_two (clip) already loaded, skipping loading.")
        else:
            logger.info("Loading tokenizer_2.")
            self.tokenizer_two = T5TokenizerFast.from_pretrained(
                args.pretrained_model_name_or_path,
                subfolder="tokenizer_2",
                revision=args.revision,
                torch_dtype=self.frozen_dtype,
            )

            logger.info("Loading text_encoder_two with %s", self.frozen_dtype)
            self.text_encoder_two = T5EncoderModel.from_pretrained(
                args.pretrained_model_name_or_path,
                subfolder="text_encoder_2",
                revision=args.revision,
                torch_dtype=self.frozen_dtype,
            )

            logger.info("Freezing text_encoder_two parameters.")
            self.text_encoder_two.requires_grad_(False)

    def _unload_text_encoders(self) -> None:
        if self.text_encoder_one is None:
            logger.info("text_encoder_one (clip) already unloaded, skipping unloading.")
        else:
            del self.tokenizer_one
            self.tokenizer_one = None
            logger.info("Unloading text_encoder_one (clip).")
            del self.text_encoder_one
            self.text_encoder_one = None
            free_memory()

        if self.text_encoder_two is None:
            logger.info("text_encoder_two (t5) already unloaded, skipping unloading.")
        else:
            del self.tokenizer_two
            self.tokenizer_two = None
            logger.info("Unloading text_encoder_two (t5).")
            del self.text_encoder_two
            self.text_encoder_two = None
            free_memory()

    def _load_vae(self) -> None:
        if self.vae is not None:
            logger.info("VAE already loaded, skipping loading.")
            return None

        logger.info("Loading vae with %s.", self.frozen_dtype)
        self.vae = AutoencoderKL.from_pretrained(
            args.pretrained_model_name_or_path,
            subfolder="vae",
            revision=args.revision,
            variant=args.variant,
            torch_dtype=self.frozen_dtype,
        )

        logger.info("Freezing vae parameters.")
        self.vae.requires_grad_(False)

        logger.info("Caching vae configuration parameters, so available even if unloaded.")
        self.vae_config_shift_factor = self.vae.config.shift_factor
        self.vae_config_scaling_factor = self.vae.config.scaling_factor
        self.vae_config_block_out_channels = self.vae.config.block_out_channels

        return self.vae

    def _unload_vae(self) -> None:
        if self.vae is None:
            logger.info("VAE already unloaded, skipping unloading.")
            return
        logger.info("Unloading vae.")
        del self.vae
        self.vae = None
        free_memory()

    def _configure_gradient_checkpointing(self) -> None:
        if self.transformer is None:
            msg = "Transformer must be loaded before configuring gradient checkpointing."
            raise RuntimeError(msg)
        if args.gradient_checkpointing:
            logger.info(
                "Enabling gradient checkpointing (a technique to save VRAM during backpropagation by not storing intermediate activations)"
            )
            self.transformer.enable_gradient_checkpointing()

    def _configure_lora_adapter(self) -> None:
        if self.transformer is None:
            msg = "Transformer must be loaded before configuring LoRA adapter."
            raise RuntimeError(msg)

        # TODO: https://github.com/griptape-ai/griptape-nodes/issues/1354
        # expose target modules...maybe or... maybe only if someone screams.
        # TODO: https://github.com/griptape-ai/griptape-nodes/issues/1354
        # I saw some awesome doc or code or something that talked about typical layers sets
        #       used by other lora training frameworks like ostris nad flux gym... where was that?
        # if args.lora_layers is not None:
        #     target_modules = [layer.strip() for layer in args.lora_layers.split(",")]  # noqa: ERA001
        # else: # noqa: ERA001
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

        # # Bare minimum target modules for FluxTransformer2DModel according to AI.
        # # I did see some interesting qualitative differences when using only these modules,
        # # I'd really like to expose this choice to the user.
        # target_modules = ["attn.to_q", "attn.to_v"] # noqa: ERA001

        # now we will add new LoRA weights the transformer layers
        logger.info("Creating lora config and adding as adapter to transformer.")
        transformer_lora_config = LoraConfig(
            r=args.rank,
            lora_alpha=args.rank,
            lora_dropout=args.lora_dropout,
            init_lora_weights="gaussian",
            target_modules=target_modules,
        )
        self.transformer.add_adapter(transformer_lora_config)

    def _log_trainable_parameters(self) -> None:
        if self.transformer is None:
            msg = "Transformer must be loaded before logging trainable parameters."
            raise RuntimeError(msg)

        trainable_params = 0
        all_param = 0
        for _, param in self.transformer.named_parameters():
            all_param += param.numel()
            if param.requires_grad:
                trainable_params += param.numel()
        logger.info(
            "trainable params: %s || all params: %s || trainable%%: %.2f",
            trainable_params,
            all_param,
            100 * trainable_params / all_param,
        )

    def _register_save_load_hooks_for_transformer(self) -> None:
        if self.accelerator is None:
            msg = "Accelerator must be configured before registering save/load hooks."
            raise RuntimeError(msg)
        if self.transformer is None:
            msg = "Transformer must be loaded before registering save/load hooks."
            raise RuntimeError(msg)

        logger.info("Registering save and load model hooks with accelerator.")
        register_save_load_hooks(self.accelerator, self.transformer)

    def _scale_learning_rate(self) -> None:
        if self.accelerator is None:
            msg = "Accelerator must be configured before scaling learning rate."
            raise RuntimeError(msg)
        if self.transformer is None:
            msg = "Transformer must be loaded before scaling learning rate."
            raise RuntimeError(msg)

    def _configure_optimizer(self) -> None:
        if self.accelerator is None:
            msg = "Accelerator must be configured before configuring optimizer."
            raise RuntimeError(msg)
        if self.transformer is None:
            msg = "Transformer must be loaded before configuring optimizer."
            raise RuntimeError(msg)

        # Optionally scale the learning rate to compensate for the gradient accumulation steps,
        # train batch size, and number of processes.
        # This is a common practice to ensure that the effective learning rate remains constant according to AI.
        if self.args.scale_lr:
            logger.info(
                "Scaling learning rate by learning_rate * gradient_accumulation_steps * train_batch_size * num_processes."
            )
            self.args.learning_rate = (
                self.args.learning_rate
                * self.args.gradient_accumulation_steps
                * self.args.train_batch_size
                * self.accelerator.num_processes
            )

        # Optimization parameters
        logger.info("Configuring optimizer.")
        transformer_lora_parameters = list(filter(lambda p: p.requires_grad, self.transformer.parameters()))
        transformer_parameters_with_lr = {"params": transformer_lora_parameters, "lr": args.learning_rate}
        params_to_optimize = [transformer_parameters_with_lr]
        self.optimizer = create_optimizer(self.accelerator, args, params_to_optimize)

    def _load_dreambooth_dataset(self) -> None:
        # Dataset and DataLoaders creation:
        logger.info("Loading dreambooth dataset.")

        if args.instance_data_dir is not None and args.dataset_name is not None:
            msg = "You cannot provide both `instance_data_dir` and `dataset_name`. Please choose one of them."
            raise ValueError(msg)

        if args.instance_data_dir is not None:
            self.train_dataset = DreamBoothDataset.from_local_directory(
                instance_data_root=args.instance_data_dir,
                instance_prompt=args.instance_prompt,
                class_prompt=args.class_prompt,
                class_data_root=args.class_data_dir if args.with_prior_preservation else None,
                class_num=args.num_class_images,
                size=args.resolution,
                repeats=args.repeats,
                center_crop=args.center_crop,
                random_flip=args.random_flip,
                resolution=args.resolution,
            )

        if args.dataset_name is not None:
            self.train_dataset = DreamBoothDataset.from_hf_dataset(
                dataset_name=args.dataset_name,
                dataset_config_name=args.dataset_config_name,
                cache_dir=args.cache_dir,
                image_column=args.image_column,
                caption_column=args.caption_column,
                instance_prompt=args.instance_prompt,
                class_prompt=args.class_prompt,
                class_data_root=args.class_data_dir if args.with_prior_preservation else None,
                class_num=args.num_class_images,
                size=args.resolution,
                repeats=args.repeats,
                center_crop=args.center_crop,
                random_flip=args.random_flip,
                resolution=args.resolution,
            )

    def _create_dataloader(self) -> None:
        if self.train_dataset is None:
            msg = "Train dataset must be loaded before creating dataloader."
            raise RuntimeError(msg)

        logger.info("Creating data loader.")
        self.train_dataloader = torch.utils.data.DataLoader(
            self.train_dataset,
            batch_size=args.train_batch_size,
            shuffle=True,
            collate_fn=lambda examples: collate_fn(examples, with_prior_preservation=args.with_prior_preservation),
            num_workers=args.dataloader_num_workers,
        )

    def _compute_text_embeddings(self, prompt: str | list[str]) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        if self.device is None:
            msg = "Device must be configured before computing text embeddings."
            raise RuntimeError(msg)
        with torch.no_grad():
            prompt_embeds, pooled_prompt_embeds, text_ids = encode_prompt(
                clip_text_encoder=self.text_encoder_one,
                t5_text_encoder=self.text_encoder_two,
                clip_tokenizer=self.tokenizer_one,
                t5_tokenizer=self.tokenizer_two,
                prompt=prompt,
                max_sequence_length=args.max_sequence_length,
            )
            prompt_embeds = prompt_embeds.to(self.device)
            pooled_prompt_embeds = pooled_prompt_embeds.to(self.device)
            text_ids = text_ids.to(self.device)
        return prompt_embeds, pooled_prompt_embeds, text_ids

    def _compute_text_embeddings_and_prior_preservation(self) -> None:
        if not self.train_dataset.custom_instance_prompts:
            instance_prompt_hidden_states, instance_pooled_prompt_embeds, instance_text_ids = (
                self._compute_text_embeddings(args.instance_prompt)
            )

            prompt_embeds = instance_prompt_hidden_states
            pooled_prompt_embeds = instance_pooled_prompt_embeds
            text_ids = instance_text_ids

            # Handle class prompt for prior-preservation.
            if args.with_prior_preservation:
                class_prompt_hidden_states, class_pooled_prompt_embeds, class_text_ids = self._compute_text_embeddings(
                    args.class_prompt
                )
                prompt_embeds = torch.cat([prompt_embeds, class_prompt_hidden_states], dim=0)
                pooled_prompt_embeds = torch.cat([pooled_prompt_embeds, class_pooled_prompt_embeds], dim=0)
                text_ids = torch.cat([text_ids, class_text_ids], dim=0)

            # Clear the memory here
            del self.text_encoder_one, self.text_encoder_two, self.tokenizer_one, self.tokenizer_two
            free_memory()

    def _cache_text_embedding(self) -> None:
        self._load_text_encoders()
        if self.text_encoder_one is None:
            msg = "Text encoder one must be loaded before caching text embeddings."
            raise RuntimeError(msg)
        if self.text_encoder_two is None:
            msg = "Text encoder two must be loaded before caching text embeddings."
            raise RuntimeError(msg)

        logger.info(
            "Copying text encoders to device %s with dtype %s for latent caching.", self.device, self.frozen_dtype
        )
        self.text_encoder_one.to(device=self.device, dtype=self.frozen_dtype)
        self.text_encoder_two.to(device=self.device, dtype=self.frozen_dtype)

        logger.info(
            "Caching text emeddings: precompute latents for dataset images, saves VRAM that would be required by the text encoders (substantial - t5 is like 10GB at f16)."
        )
        logger.info(
            "  with the tradeoff of not being able to include text encoder layers in lora, but we're not doing that anyway."
        )
        self.text_embeddings_cache = []
        for batch in tqdm(self.train_dataloader, desc="Caching text embeddings"):
            with torch.no_grad():
                prompt_embeds, pooled_prompt_embeds, text_ids = self._compute_text_embeddings(batch["prompts"])
                self.text_embeddings_cache.append((prompt_embeds, pooled_prompt_embeds, text_ids))

        self._unload_text_encoders()

    def _cache_latents(self) -> None:
        if args.cache_latents:
            self._load_vae()
            if self.vae is None:
                msg = "VAE must be loaded before caching latents."
                raise RuntimeError(msg)

            logger.info("Copying VAE to device %s with dtype %s for latent caching.", self.device, self.frozen_dtype)
            self.vae.to(self.device, dtype=self.frozen_dtype)

            logger.info(
                "Caching latents: precompute latents for dataset images, saves VRAM that would be required by VAE."
            )
            self.latents_cache = []
            for batch in tqdm(self.train_dataloader, desc="Caching latents"):
                with torch.no_grad():
                    batch["pixel_values"] = batch["pixel_values"].to(
                        self.device, non_blocking=True, dtype=self.frozen_dtype
                    )
                    self.latents_cache.append(self.vae.encode(batch["pixel_values"]).latent_dist)

            self._unload_vae()

    def _determine_number_scheduler_steps(self) -> None:
        if self.accelerator is None:
            msg = "Accelerator must be configured before determining number of scheduler steps."
            raise RuntimeError(msg)

        if self.accelerator.num_processes != 1:
            msg = (
                "We assume a single process in the train flux lora parameters script. "
                "I don't see why this would be useful with the current scope of training"
            )
            raise RuntimeError(msg)
        len_train_dataloader_after_sharding = math.ceil(len(self.train_dataloader) / self.accelerator.num_processes)
        self.num_update_steps_per_epoch = math.ceil(
            len_train_dataloader_after_sharding / args.gradient_accumulation_steps
        )
        self.num_training_steps_for_scheduler = (
            args.num_train_epochs * self.accelerator.num_processes * self.num_update_steps_per_epoch
        )

        if self.args.max_train_steps is not None:
            self.num_training_steps_for_scheduler = min(self.num_training_steps_for_scheduler, args.max_train_steps)

        logger.info("Number of training steps for scheduler: %d", self.num_training_steps_for_scheduler)

    def _configure_scheduler(self) -> None:
        if self.optimizer is None:
            msg = "Optimizer must be configured before configuring scheduler."
            raise RuntimeError(msg)
        if self.num_training_steps_for_scheduler is None:
            msg = "Number of training steps must be determined before configuring scheduler."
            raise RuntimeError(msg)

        logger.info("Configuring scheduler.")
        self.lr_scheduler = get_scheduler(
            args.lr_scheduler,
            optimizer=self.optimizer,
            num_warmup_steps=0,
            num_training_steps=self.num_training_steps_for_scheduler,
            num_cycles=args.lr_num_cycles,
            power=args.lr_power,
        )

    def _prepare_for_accelerator(self) -> None:
        if self.accelerator is None:
            msg = "Accelerator must be configured before preparing for accelerator."
            raise RuntimeError(msg)
        if self.transformer is None:
            msg = "Transformer must be loaded before preparing for accelerator."
            raise RuntimeError(msg)
        if self.optimizer is None:
            msg = "Optimizer must be configured before preparing for accelerator."
            raise RuntimeError(msg)
        if self.train_dataloader is None:
            msg = "Train dataloader must be created before preparing for accelerator."
            raise RuntimeError(msg)
        if self.lr_scheduler is None:
            msg = "Learning rate scheduler must be configured before preparing for accelerator."
            raise RuntimeError(msg)

        needs_cpu_offload = False
        if torch.cuda.is_available():
            logger.info("Memory details just before accelerator.prepare")
            free_mem, total_mem = torch.cuda.mem_get_info()
            logger.info("Total memory: %s", to_human_readable_size(total_mem))
            logger.info("Free memory: %s", to_human_readable_size(free_mem))
            logger.info("Transformer size: %s", human_readable_memory_footprint(self.transformer))
            logger.info("Applying layerwise casting to fp8 to save VRAM.")
            self.transformer.enable_layerwise_casting(
                storage_dtype=torch.float8_e4m3fn,
                compute_dtype=self.frozen_dtype,
            )
            logger.info("New transformer size: %s", human_readable_memory_footprint(self.transformer))

            transformer_mem = self.transformer.get_memory_footprint()
            required_mem = transformer_mem
            mem_left = free_mem - required_mem
            if required_mem < free_mem:
                logger.info(
                    "Congratulations you'll have up to %s to spare after accelerate prepare!",
                    to_human_readable_size(free_mem - required_mem),
                )
            else:
                msg = (
                    f"Not enough VRAM. "
                    f"Required memory: {to_human_readable_size(required_mem)}, "
                    f"Free memory: {to_human_readable_size(free_mem)}."
                )
                raise RuntimeError(msg)
            cpu_offload_threshold = 2_000_000_000
            needs_cpu_offload = mem_left < cpu_offload_threshold

        # Prepare everything with our `accelerator`.
        # This should only be called ONCE. Do not refactor for locality.
        logger.info("Preparing transformer, optimizer, train_dataloader and lr_scheduler with accelerator.")
        (
            self.transformer,
            self.optimizer,
            self.train_dataloader,
            self.lr_scheduler,
        ) = self.accelerator.prepare(self.transformer, self.optimizer, self.train_dataloader, self.lr_scheduler)

        logger.info(
            "transformer %s %s %s",
            self.transformer.device.type,
            self.transformer.dtype,
            human_readable_memory_footprint(self.transformer),
        )

        if needs_cpu_offload:
            logger.info(
                "Applying CPU offload to non LoRA modules of the transformer to save VRAM because we're cutting it too close."
            )
            apply_cpu_offload_to_non_lora_modules(self.transformer, torch.device("cuda"))

    def _initialize_trackers(self) -> None:
        if self.accelerator is None:
            msg = "Accelerator must be configured before initializing trackers."
            raise RuntimeError(msg)

        logger.info("Initializing trackers.")
        if self.accelerator.is_main_process:
            tracker_name = "flux-lora-dreambooth"
            self.accelerator.init_trackers(tracker_name, config=vars(args))

    def _log_training_start_summary(self) -> None:
        if self.train_dataset is None:
            msg = "Train dataset must be loaded before logging training start summary."
            raise RuntimeError(msg)
        if self.train_dataloader is None:
            msg = "Train dataloader must be created before logging training start summary."
            raise RuntimeError(msg)

        args = self.args
        logger.info("***** Running training *****")
        logger.info("  Num examples = %d", len(self.train_dataset))
        logger.info("  Num batches each epoch = %d", len(self.train_dataloader))
        logger.info("  Num Epochs = %d", args.num_train_epochs)
        logger.info("  Instantaneous batch size per device = %d", args.train_batch_size)
        logger.info("  Gradient Accumulation steps = %d", args.gradient_accumulation_steps)
        logger.info("  Total optimization steps = %d", args.max_train_steps)

    def _load_checkpoint_or_default(self) -> tuple[int, int, int]:
        if self.accelerator is None:
            msg = "Accelerator must be configured before trying to load checkpoint."
            raise RuntimeError(msg)

        if not args.resume_from_checkpoint:
            self.initial_global_step = 0
            self.global_step = 0
            self.first_epoch = 0
            return self.initial_global_step, self.global_step, self.first_epoch

        # Potentially load in the weights and states from a previous save
        logger.info("  Resume from checkpoint %s", args.resume_from_checkpoint)

        if args.resume_from_checkpoint != "latest":
            path = Path(args.resume_from_checkpoint)
        else:
            # Get the mos recent checkpoint
            dirs = list(Path(args.output_dir).iterdir())
            dirs = [d for d in dirs if d.name.startswith("checkpoint")]
            dirs = sorted(dirs, key=lambda x: int(x.name.split("-")[1]))
            path = dirs[-1] if len(dirs) > 0 else None

        if path is None:
            self.accelerator.print(
                f"Checkpoint '{args.resume_from_checkpoint}' does not exist. Starting a new training run."
            )
            args.resume_from_checkpoint = None
            self.initial_global_step = 0
            self.global_step = 0
            self.first_epoch = 0
            return self.initial_global_step, self.global_step, self.first_epoch

        self.accelerator.print(f"Resuming from checkpoint {path}")
        self.accelerator.load_state(str(Path(args.output_dir) / path))

        self.global_step = int(path.name.split("-")[1])
        self.initial_global_step = self.global_step
        self.first_epoch = self.global_step // self.num_update_steps_per_epoch

        return self.initial_global_step, self.global_step, self.first_epoch

    def _init_steps_progress_bar(self, initial_global_step: int) -> tqdm:
        if self.accelerator is None:
            msg = "Accelerator must be configured before starting training."
            raise RuntimeError(msg)

        progress_bar = tqdm(
            range(self.num_training_steps_for_scheduler),
            initial=initial_global_step,
            desc="Train Steps",
            # Only show the progress bar once on each machine.
            disable=not self.accelerator.is_local_main_process,
        )
        return progress_bar

    def _get_sigmas(self, timesteps: torch.Tensor, n_dim: int = 4, dtype: torch.dtype = torch.float32) -> torch.Tensor:
        if self.accelerator is None:
            msg = "Accelerator must be configured before getting sigmas."
            raise RuntimeError(msg)
        if self.noise_scheduler_copy is None:
            msg = "Noise scheduler copy must be created before getting sigmas."
            raise RuntimeError(msg)

        sigmas = self.noise_scheduler_copy.sigmas.to(device=self.accelerator.device, dtype=dtype)
        schedule_timesteps = self.noise_scheduler_copy.timesteps.to(self.accelerator.device)
        timesteps = timesteps.to(self.accelerator.device)
        step_indices = [(schedule_timesteps == t).nonzero().item() for t in timesteps]

        sigma = sigmas[step_indices].flatten()
        while len(sigma.shape) < n_dim:
            sigma = sigma.unsqueeze(-1)
        return sigma

    def _train(self) -> None:
        if self.accelerator is None:
            msg = "Accelerator must be configured before starting training."
            raise RuntimeError(msg)

        initial_global_step, global_step, first_epoch = self._load_checkpoint_or_default()
        progress_bar = self._init_steps_progress_bar(initial_global_step)

        logger.info("Starting training")
        for epoch in range(first_epoch, args.num_train_epochs):
            self.transformer.train()

            for step, batch in enumerate(self.train_dataloader):
                loss = self._step(step, batch)

                # Checks if the accelerator has performed an optimization step behind the scenes
                if self.accelerator.sync_gradients:
                    progress_bar.update(1)
                    global_step += 1

                    self._save_checkpoint(global_step)

                logs = {"loss": loss.detach().item(), "lr": self.lr_scheduler.get_last_lr()[0]}
                progress_bar.set_postfix(**logs)
                self.accelerator.log(logs, step=global_step)

                if global_step >= args.max_train_steps:
                    break

            # At the end of each epoch, we optionally generate and publish validation images.
            if args.validation_prompt is not None and epoch % args.validation_epochs == 0:
                self._publish_validation_images(phase="training", epoch=epoch)

    def _step(self, step: int, batch: dict) -> Any:  # noqa: C901,PLR0912,PLR0915
        if self.accelerator is None:
            msg = "Accelerator must be configured before stepping."
            raise RuntimeError(msg)
        if self.transformer is None:
            msg = "Transformer must be loaded before stepping."
            raise RuntimeError(msg)
        if self.optimizer is None:
            msg = "Optimizer must be configured before stepping."
            raise RuntimeError(msg)
        if self.train_dataloader is None:
            msg = "Train dataloader must be created before stepping."
            raise RuntimeError(msg)
        if self.lr_scheduler is None:
            msg = "Learning rate scheduler must be configured before stepping."
            raise RuntimeError(msg)
        if self.vae_config_shift_factor is None:
            msg = "VAE config shift factor must be set before stepping."
            raise RuntimeError(msg)
        if self.vae_config_scaling_factor is None:
            msg = "VAE config scaling factor must be set before stepping."
            raise RuntimeError(msg)
        if self.vae_config_block_out_channels is None:
            msg = "VAE config block out channels must be set before stepping."
            raise RuntimeError(msg)

        with self.accelerator.accumulate([self.transformer]):
            # encode batch prompts when custom prompts are provided for each image -
            if self.train_dataset.custom_instance_prompts:
                # TODO: https://github.com/griptape-ai/griptape-nodes/issues/1354
                #       Make text embeddings caching optional.
                prompt_embeds, pooled_prompt_embeds, text_ids = self.text_embeddings_cache[step]
            else:
                # TODO: https://github.com/griptape-ai/griptape-nodes/issues/1354
                #       Make per-image prompts optional.
                msg = (
                    "Custom instance prompts are not provided. "
                    "Please provide custom prompts for each image in the dataset."
                )
                raise ValueError(msg)

            # Convert images to latent space
            if args.cache_latents:
                model_input = self.latents_cache[step].sample()
            else:
                if self.vae is None:
                    msg = "VAE must be loaded before stepping if caching latents is disabled."
                    raise RuntimeError(msg)
                pixel_values = batch["pixel_values"].to(dtype=self.vae.dtype)
                model_input = self.vae.encode(pixel_values).latent_dist.sample()
            model_input = (model_input - self.vae_config_shift_factor) * self.vae_config_scaling_factor
            model_input = model_input.to(dtype=self.frozen_dtype)

            vae_scale_factor = 2 ** (len(self.vae_config_block_out_channels) - 1)

            latent_image_ids = diffusers.FluxPipeline._prepare_latent_image_ids(
                model_input.shape[0],
                model_input.shape[2] // 2,
                model_input.shape[3] // 2,
                self.accelerator.device,
                self.frozen_dtype,
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
            indices = (u * self.noise_scheduler_copy.config.num_train_timesteps).long()
            timesteps = self.noise_scheduler_copy.timesteps[indices].to(device=model_input.device)

            # Add noise according to flow matching.
            # zt = (1 - texp) * x + texp * z1  # noqa: ERA001
            sigmas = self._get_sigmas(timesteps, n_dim=model_input.ndim, dtype=model_input.dtype)
            noisy_model_input = (1.0 - sigmas) * model_input + sigmas * noise

            packed_noisy_model_input = diffusers.FluxPipeline._pack_latents(
                noisy_model_input,
                batch_size=model_input.shape[0],
                num_channels_latents=model_input.shape[1],
                height=model_input.shape[2],
                width=model_input.shape[3],
            )

            # handle guidance
            if self._unwrap_model(self.transformer).config.guidance_embeds:  # type: ignore[reportAttributeAccessIssue]
                guidance = torch.tensor([args.guidance_scale], device=self.accelerator.device)
                guidance = guidance.expand(model_input.shape[0])
            else:
                guidance = None

            # Predict the noise residual
            model_pred = self.transformer(
                hidden_states=packed_noisy_model_input,
                # YiYi notes: divide it by 1000 for now because we scale it by 1000 in the transformer model (we should not keep it but I want to keep the inputs same for the model for testing)
                timestep=timesteps / 1000,
                guidance=guidance,
                pooled_projections=pooled_prompt_embeds,
                encoder_hidden_states=prompt_embeds,
                txt_ids=text_ids,
                img_ids=latent_image_ids,
                return_dict=False,
            )[0]
            model_pred = diffusers.FluxPipeline._unpack_latents(
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

            # Compute regular loss.
            loss = torch.mean(
                (weighting.float() * (model_pred.float() - target.float()) ** 2).reshape(target.shape[0], -1),
                1,
            )
            loss = loss.mean()

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

                # Add the prior loss to the instance loss.
                loss = loss + args.prior_loss_weight * prior_loss

            self.accelerator.backward(loss)

            if self.accelerator.sync_gradients:
                params_to_clip = self.transformer.parameters()
                self.accelerator.clip_grad_norm_(params_to_clip, args.max_grad_norm)

            self.optimizer.step()
            self.lr_scheduler.step()
            self.optimizer.zero_grad()

        return loss

    def _unwrap_model(self, model: torch.nn.Module) -> torch.nn.Module:
        if self.accelerator is None:
            msg = "Accelerator must be configured before unwrapping model."
            raise RuntimeError(msg)
        return unwrap_model(self.accelerator, model)

    def _save_checkpoint(self, global_step: int) -> None:
        if self.accelerator is None:
            msg = "Accelerator must be configured before saving checkpoint."
            raise RuntimeError(msg)

        if self.accelerator.is_main_process and global_step % args.checkpointing_steps == 0:
            # _before_ saving state, check if this save would set us over the `checkpoints_total_limit`
            if args.checkpoints_total_limit is not None:
                checkpoints = list(Path(args.output_dir).iterdir())
                checkpoints = [d for d in checkpoints if d.name.startswith("checkpoint")]
                checkpoints = sorted(checkpoints, key=lambda x: int(x.name.split("-")[1]))

                # before we save the new checkpoint, we need to have at _most_ `checkpoints_total_limit - 1` checkpoints
                if len(checkpoints) >= args.checkpoints_total_limit:
                    num_to_remove = len(checkpoints) - args.checkpoints_total_limit + 1
                    removing_checkpoints = checkpoints[0:num_to_remove]

                    logger.info(
                        "%d checkpoints already exist, removing %d checkpoints",
                        len(checkpoints),
                        len(removing_checkpoints),
                    )
                    logger.info("removing checkpoints: %s", ", ".join([str(x) for x in removing_checkpoints]))

                    for removing_checkpoint in removing_checkpoints:
                        shutil.rmtree(Path(args.output_dir) / removing_checkpoint)

            save_path = Path(args.output_dir) / f"checkpoint-{global_step}"
            self.accelerator.save_state(str(save_path))
            logger.info("Saved state to %s", save_path)

    def _publish_validation_images(self, phase: str, epoch: int | None) -> list[Image]:
        if self.accelerator is None:
            msg = "Accelerator must be configured before logging validation."
            raise RuntimeError(msg)
        if self.text_encoder_one is None:
            msg = "Text encoder one must be loaded before logging validation."
            raise RuntimeError(msg)
        if self.text_encoder_two is None:
            msg = "Text encoder two must be loaded before logging validation."
            raise RuntimeError(msg)

        if not self.accelerator.is_main_process:
            return []

        logger.info(
            "Running validation... \n Generating %d images with prompt: %s.",
            args.num_validation_images,
            args.validation_prompt,
        )

        pipeline = diffusers.FluxPipeline.from_pretrained(
            args.pretrained_model_name_or_path,
            vae=self.vae,
            text_encoder=self.text_encoder_one,  # self._unwrap_model(self.text_encoder_one),
            text_encoder_2=self.text_encoder_two,  # self._unwrap_model(),
            transformer=self.transformer,  # self._unwrap_model(self.transformer),
            revision=args.revision,
            variant=args.variant,
            torch_dtype=self.frozen_dtype,
        )
        pipeline_args = {"prompt": args.validation_prompt}

        pipeline.set_progress_bar_config(disable=True)

        # run inference
        generator = (
            torch.Generator(device=self.accelerator.device).manual_seed(args.seed) if args.seed is not None else None
        )
        autocast_ctx = torch.autocast(self.accelerator.device.type) if phase != "final" else nullcontext()

        # pre-calculate  prompt embeds, pooled prompt embeds, text ids because t5 does not support autocast
        logger.info("Encoding prompt...")
        with torch.no_grad():
            prompt_embeds, pooled_prompt_embeds, text_ids = pipeline.encode_prompt(
                pipeline_args["prompt"], prompt_2=pipeline_args["prompt"]
            )

        num_inference_steps = self.args.num_validation_inference_steps

        def callback_on_step_end(
            pipe: diffusers.FluxPipeline,  # noqa: ARG001
            i: int,
            _t: Any,
            callback_kwargs: dict,  # noqa: ARG001
        ) -> dict:
            if i < num_inference_steps - 1:
                # self.pipe_params.publish_output_image_preview_latents(pipe, callback_kwargs["latents"])  # noqa: ERA001
                logger.info("Starting inference step %d of %d...", i + 2, num_inference_steps)
            return {}

        images = []
        image_paths = []
        for i in range(args.num_validation_images):
            logger.info("Generating image %d/%d", i + 1, args.num_validation_images)
            with autocast_ctx:
                image = pipeline(
                    prompt_embeds=prompt_embeds,
                    pooled_prompt_embeds=pooled_prompt_embeds,
                    generator=generator,
                    num_inference_steps=self.args.num_validation_inference_steps,
                    callback_on_step_end=callback_on_step_end,
                ).images[0]
                images.append(image)
                image_paths.append(Path(args.output_dir) / f"image_{epoch}_{i}_{phase}.png")
                image.save(image_paths[-1])

        logger.info("Uploading images to trackers")
        for tracker in self.accelerator.trackers:
            if tracker.name == "stdout":
                tracker.log(
                    {
                        "type": "image",
                        "phase": phase,
                        "image_paths": image_paths,
                    }
                )

        # Clean up the pipeline to free memory.
        del pipeline
        free_memory()

        return images

    def _save_lora_weights(self) -> None:
        if self.accelerator is None:
            msg = "Accelerator must be configured before saving LoRA weights."
            raise RuntimeError(msg)

        if self.accelerator.is_main_process:
            logger.info("Saving the LoRA weights")
            transformer = unwrap_model(self.accelerator, self.transformer)

            # Move the lora modules back to the cpu before saving.
            # We move only the lora modules for two reasons:
            # 1. If we ended up needing to apply cpu offloading to the non-lora modules to save VRAM, then
            #    the non-lora modules will have device type "meta" and we won't be able to recover them (afaik).
            # 2. If we didn't apply cpu offloading and we need to upcast the transformer to fp32 before saving,
            #    then the transformer may be too large to fit on the GPU if we trained using fp16 or bf16 (it will be close on most consumer gpus).
            #    Specifically, upcasting from fp16 to fp32 will double the size of the model, and if we trained using fp8 it will quadruple the size.
            lora_modules_to(
                transformer, device="cpu", dtype=(torch.float32 if args.upcast_before_saving else self.trainable_dtype)
            )
            diffusers.FluxPipeline.save_lora_weights(
                save_directory=args.output_dir,
                transformer_lora_layers=get_peft_model_state_dict(transformer),
                weight_name="pytorch_lora_weights.safetensors",
            )

            del transformer
            free_memory()

    def run(self) -> None:
        # Configure accelerator, torch, and environment.
        self._configure_accelerator()
        self._configure_device()
        self._set_seed()
        if self.accelerator is None:
            msg = "Accelerator must be configured before starting training."
            raise RuntimeError(msg)

        with gpu_vram_profiling(self.args.snapshot_html_path):
            # Load and configure the model for training.
            self._load_schedulers()
            self._load_transformer()
            self._configure_gradient_checkpointing()
            self._configure_lora_adapter()
            self._log_trainable_parameters()
            self._register_save_load_hooks_for_transformer()

            # Create and configure the optimizer.
            self._configure_optimizer()

            # Load and prepare the training data.
            self._load_dreambooth_dataset()
            self._create_dataloader()
            self._compute_text_embeddings_and_prior_preservation()
            self._cache_text_embedding()
            self._cache_latents()

            # Configure the noise scheduler.
            self._determine_number_scheduler_steps()
            self._configure_scheduler()

            # Prepare for accelerator.
            # From docs:
            #   - Prepare all objects passed in args for distributed training and mixed precision, then return them in the same order.
            #   - You dont need to prepare a model if you only use it for inference without any kind of mixed precision
            self._prepare_for_accelerator()

            # Initialize training progress tracker(s).
            self._initialize_trackers()

            # Training
            self._log_training_start_summary()
            self._train()

            self.accelerator.wait_for_everyone()
            self._save_lora_weights()
            if args.validation_prompt:
                self._publish_validation_images(phase="final", epoch=None)
            self.accelerator.end_training()


if __name__ == "__main__":
    args = parse_args()
    training_script = FluxLoraTrainingScript(args)
    training_script.run()
