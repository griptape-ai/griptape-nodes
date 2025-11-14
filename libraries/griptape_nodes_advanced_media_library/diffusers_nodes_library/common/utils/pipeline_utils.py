import contextlib
import gc
import logging

import torch  # type: ignore[reportMissingImports]
from diffusers.pipelines.pipeline_utils import DiffusionPipeline  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.utils.torch_utils import (
    create_device_map_for_pipeline,
    get_best_device,
    get_devices,
    get_free_cuda_memory,
    get_max_memory_footprint,
    get_total_memory_footprint,
    should_enable_attention_slicing,
    to_human_readable_size,
)

logger = logging.getLogger("griptape_nodes")

# Best guess for memory optimization with 20% headroom
# https://huggingface.co/docs/accelerate/en/usage_guides/model_size_estimator#caveats-with-this-calculator
MEMORY_HEADROOM_FACTOR = 1.2


def get_pipeline_component_names(pipe: DiffusionPipeline) -> list[str]:
    """Get component names dynamically from pipeline."""
    component_names = []

    for attr_name in dir(pipe):
        if not attr_name.startswith("_"):
            try:
                attr = getattr(pipe, attr_name)
                if hasattr(attr, "to") and callable(attr.to) and hasattr(attr, "parameters"):
                    component_names.append(attr_name)
            except Exception:
                logger.debug("Error accessing attribute %s of pipeline: %s", attr_name, pipe)
                continue

    if not component_names:
        logger.warning("Could not determine pipeline component names dynamically, using defaults.")
        component_names = ["vae", "text_encoder", "text_encoder_2", "transformer", "controlnet"]

    logger.debug("Detected pipeline components: %s", component_names)
    return component_names


def _check_cuda_memory_sufficient(
    pipe: DiffusionPipeline,
) -> bool:
    """Check if CUDA device has sufficient memory for the pipeline."""
    model_memory = MEMORY_HEADROOM_FACTOR * get_total_memory_footprint(pipe, get_pipeline_component_names(pipe))
    return model_memory <= get_free_cuda_memory()


def _check_mps_memory_sufficient(
    pipe: DiffusionPipeline,
) -> bool:
    """Check if MPS device has sufficient memory for the pipeline."""
    model_memory = get_total_memory_footprint(pipe, get_pipeline_component_names(pipe))
    recommended_max_memory = torch.mps.recommended_max_memory()
    free_memory = recommended_max_memory - torch.mps.current_allocated_memory()
    return model_memory <= free_memory


def _log_memory_info(
    pipe: DiffusionPipeline,
    device: torch.device,
) -> None:
    """Log memory information for the device."""
    model_memory = MEMORY_HEADROOM_FACTOR * get_total_memory_footprint(pipe, get_pipeline_component_names(pipe))

    if device.type == "cuda":
        total_memory = torch.cuda.get_device_properties(device).total_memory
        free_memory = total_memory - torch.cuda.memory_allocated(device)
        logger.info("Total memory on %s: %s", device, to_human_readable_size(total_memory))
        logger.info("Free memory on %s: %s", device, to_human_readable_size(free_memory))
    elif device.type == "mps":
        recommended_max_memory = torch.mps.recommended_max_memory()
        free_memory = recommended_max_memory - torch.mps.current_allocated_memory()
        logger.info("Recommended max memory on %s: %s", device, to_human_readable_size(recommended_max_memory))
        logger.info("Free memory on %s: %s", device, to_human_readable_size(free_memory))

    logger.info("Require memory for diffusion pipeline: %s", to_human_readable_size(model_memory))


def _quantize_diffusion_pipeline(
    pipe: DiffusionPipeline,
    quantization_mode: str,
    device: torch.device,
) -> None:
    """Uses optimum.quanto to quantize the pipeline components."""
    from optimum.quanto import freeze, qfloat8, qint4, qint8, quantize  # type: ignore[reportMissingImports]

    logger.info("Applying quantization: %s", quantization_mode)
    _log_memory_info(pipe, device)
    quant_map = {"fp8": qfloat8, "int8": qint8, "int4": qint4}
    quant_type = quant_map[quantization_mode]

    component_names = get_pipeline_component_names(pipe)
    logger.debug("Quantizing components: %s", component_names)
    for name in component_names:
        component = getattr(pipe, name, None)
        if component is not None:
            logger.debug("Quantizing %s with %s", name, quantization_mode)
            quantize(component, weights=quant_type, exclude=["proj_out"])
            logger.debug("Freezing %s", name)
            freeze(component)
            logger.debug("Quantizing completed for %s.", name)
    logger.info("Quantization complete.")


def _automatic_optimize_diffusion_pipeline(  # noqa: C901 PLR0912 PLR0915
    pipe: DiffusionPipeline,
    device: torch.device,
) -> None:
    """Optimize pipeline memory footprint with incremental VRAM checking."""
    if device.type == "cuda":
        _log_memory_info(pipe, device)

        # Step 1: Enable attention slicing (minimal impact on quality)
        if hasattr(pipe, "enable_attention_slicing") and should_enable_attention_slicing(device):
            logger.info("Enabling attention slicing")
            pipe.enable_attention_slicing()

        # Step 2: Enable VAE slicing (processes VAE in smaller batches)
        if hasattr(pipe, "enable_vae_slicing"):
            logger.info("Enabling VAE slicing")
            pipe.enable_vae_slicing()
        elif hasattr(pipe, "vae") and hasattr(pipe.vae, "enable_slicing"):
            logger.info("Enabling VAE slicing via vae.enable_slicing()")
            pipe.vae.enable_slicing()

        # Step 3: Enable VAE tiling (critical for large images/videos)
        if hasattr(pipe, "enable_vae_tiling"):
            logger.info("Enabling VAE tiling")
            pipe.enable_vae_tiling()
        elif hasattr(pipe, "vae") and hasattr(pipe.vae, "enable_tiling"):
            logger.info("Enabling VAE tiling via vae.enable_tiling()")
            pipe.vae.enable_tiling()

        # Clear cache after enabling optimizations
        torch.cuda.empty_cache()
        gc.collect()

        # Check if slicing/tiling is sufficient
        if _check_cuda_memory_sufficient(pipe):
            logger.info("Sufficient memory after slicing/tiling. Moving pipeline to %s", device)
            pipe.to(device)
            return

        # Step 4: Try layerwise casting for transformer-based pipelines (Flux, etc.)
        if hasattr(pipe, "transformer"):
            logger.warning("Insufficient memory. Enabling fp8 layerwise casting for transformer")
            pipe.transformer.enable_layerwise_casting(
                storage_dtype=torch.float8_e4m3fn,
                compute_dtype=torch.bfloat16,
            )
            torch.cuda.empty_cache()
            gc.collect()
            _log_memory_info(pipe, device)
            if _check_cuda_memory_sufficient(pipe):
                logger.info("Sufficient memory after fp8 optimization. Moving pipeline to %s", device)
                pipe.to(device)
                return

        # Step 5: Try CPU offloading (most aggressive memory saving)
        logger.info("Insufficient memory. Trying CPU offloading techniques.")
        free_cuda_memory = get_free_cuda_memory()
        max_memory_footprint_with_headroom = MEMORY_HEADROOM_FACTOR * get_max_memory_footprint(
            pipe, get_pipeline_component_names(pipe)
        )
        logger.info("Free CUDA memory: %s", to_human_readable_size(free_cuda_memory))
        logger.info(
            "Pipeline estimated max memory footprint: %s",
            to_human_readable_size(max_memory_footprint_with_headroom),
        )

        # Try sequential offload first (most aggressive, moves submodules)
        if hasattr(pipe, "enable_sequential_cpu_offload"):
            logger.info("Enabling sequential CPU offload (most aggressive)")
            pipe.enable_sequential_cpu_offload()
            torch.cuda.empty_cache()
            gc.collect()
            logger.info("Sequential CPU offload enabled successfully")
            return

        # Fall back to model offload if sequential not available and max component fits
        if max_memory_footprint_with_headroom < free_cuda_memory and hasattr(pipe, "enable_model_cpu_offload"):
            logger.info("Enabling model CPU offload")
            pipe.enable_model_cpu_offload()
            torch.cuda.empty_cache()
            gc.collect()
            logger.info("Model CPU offload enabled successfully")
            return

        # Final fallback: load to GPU and hope for the best
        logger.warning("Memory may still be insufficient after all optimizations, but will try loading to GPU")
        pipe.to(device)

    elif device.type == "mps":
        _log_memory_info(pipe, device)

        if _check_mps_memory_sufficient(pipe):
            logger.info("Sufficient memory on %s for Pipeline.", device)
            logger.info("Moving pipeline to %s", device)
            pipe.to(device)
            return

        logger.warning("Insufficient memory on %s for Pipeline.", device)

        # Enable VAE slicing
        if hasattr(pipe, "enable_vae_slicing"):
            logger.info("Enabling VAE slicing")
            pipe.enable_vae_slicing()

        # Enable VAE tiling
        if hasattr(pipe, "enable_vae_tiling"):
            logger.info("Enabling VAE tiling")
            pipe.enable_vae_tiling()
        elif hasattr(pipe, "vae") and hasattr(pipe.vae, "enable_tiling"):
            logger.info("Enabling VAE tiling via vae.enable_tiling()")
            pipe.vae.enable_tiling()

        # Final check after VAE optimizations
        if not _check_mps_memory_sufficient(pipe):
            logger.warning("Memory may still be insufficient after optimizations, but will try anyway")

        pipe.to(device)
    return


def _manual_optimize_diffusion_pipeline(  # noqa: C901 PLR0912 PLR0913
    pipe: DiffusionPipeline,
    device: torch.device,
    *,
    attention_slicing: bool,
    vae_slicing: bool,
    transformer_layerwise_casting: bool,
    cpu_offload_strategy: str,
    quantization_mode: str,
) -> None:
    if quantization_mode != "None":
        _quantize_diffusion_pipeline(pipe, quantization_mode, device)
    if attention_slicing and hasattr(pipe, "enable_attention_slicing"):
        logger.info("Enabling attention slicing")
        pipe.enable_attention_slicing()
    if vae_slicing:
        if hasattr(pipe, "enable_vae_slicing"):
            logger.info("Enabling vae slicing")
            pipe.enable_vae_slicing()
        elif hasattr(pipe, "vae") and hasattr(pipe.vae, "use_slicing"):
            logger.info("Enabling vae slicing")
            pipe.vae.enable_slicing()
        elif hasattr(pipe, "vae"):
            logger.debug("VAE does not support slicing (e.g., AutoencoderKLTemporalDecoder), skipping")
    if transformer_layerwise_casting and hasattr(pipe, "transformer"):
        logger.info("Enabling fp8 layerwise casting for transformer")
        pipe.transformer.enable_layerwise_casting(
            storage_dtype=torch.float8_e4m3fn,
            compute_dtype=torch.bfloat16,
        )
    if cpu_offload_strategy == "Sequential":
        if hasattr(pipe, "enable_sequential_cpu_offload"):
            logger.info("Enabling sequential cpu offload")
            pipe.enable_sequential_cpu_offload()
        else:
            logger.warning("Pipeline does not support sequential cpu offload")
    elif cpu_offload_strategy == "Model":
        if hasattr(pipe, "enable_model_cpu_offload"):
            logger.info("Enabling model cpu offload")
            pipe.enable_model_cpu_offload()
        else:
            logger.warning("Pipeline does not support model cpu offload")
    elif cpu_offload_strategy == "None":
        pipe.to(device)


def distribute_pipeline_across_gpus(
    pipe: DiffusionPipeline,
    *,
    num_gpus: int | None = None,
) -> None:
    """Distribute pipeline components across multiple GPUs.

    Args:
        pipe: The diffusion pipeline to distribute
        num_gpus: Number of GPUs to use. If None, uses all available GPUs.
    """
    component_names = get_pipeline_component_names(pipe)
    device_map = create_device_map_for_pipeline(component_names, num_gpus)

    if all(device == "cpu" for device in device_map.values()):
        logger.info("No GPUs available, keeping pipeline on CPU")
        return

    logger.info("Distributing pipeline across GPUs with device_map: %s", device_map)

    for component_name, device_id in device_map.items():
        if hasattr(pipe, component_name):
            component = getattr(pipe, component_name)
            if component is not None:
                if isinstance(device_id, int):
                    target_device = torch.device(f"cuda:{device_id}")
                else:
                    target_device = torch.device(device_id)
                logger.debug("Moving %s to %s", component_name, target_device)
                component.to(target_device)


def optimize_diffusion_pipeline(  # noqa: C901 PLR0913
    pipe: DiffusionPipeline,
    *,
    memory_optimization_strategy: str = "Manual",
    attention_slicing: bool = False,
    vae_slicing: bool = False,
    transformer_layerwise_casting: bool = False,
    cpu_offload_strategy: str = "None",
    quantization_mode: str = "None",
    use_multi_gpu: bool = True,
    num_gpus: int | None = None,
) -> None:
    """Optimize pipeline performance and memory.

    Args:
        pipe: The diffusion pipeline to optimize
        memory_optimization_strategy: "Automatic" or "Manual"
        attention_slicing: Enable attention slicing
        vae_slicing: Enable VAE slicing
        transformer_layerwise_casting: Enable FP8 layerwise casting for transformer
        cpu_offload_strategy: "None", "Model", or "Sequential"
        quantization_mode: "None", "fp8", "int8", or "int4"
        use_multi_gpu: If True, distribute pipeline across multiple GPUs
        num_gpus: Number of GPUs to use for multi-GPU distribution
    """
    if use_multi_gpu:
        devices = get_devices(num_gpus=num_gpus)
        if len(devices) > 1 and all(d.type == "cuda" for d in devices):
            logger.info("Using multi-GPU mode with %s GPUs", len(devices))
            distribute_pipeline_across_gpus(pipe, num_gpus=num_gpus)

            if attention_slicing and hasattr(pipe, "enable_attention_slicing"):
                logger.info("Enabling attention slicing")
                pipe.enable_attention_slicing()
            if vae_slicing:
                if hasattr(pipe, "enable_vae_slicing"):
                    logger.info("Enabling vae slicing")
                    pipe.enable_vae_slicing()
                elif hasattr(pipe, "vae") and hasattr(pipe.vae, "enable_slicing"):
                    logger.info("Enabling vae slicing")
                    pipe.vae.enable_slicing()

            try:
                torch.backends.cuda.matmul.allow_tf32 = True
                if hasattr(torch.backends.cuda, "sdp_kernel"):
                    torch.backends.cuda.sdp_kernel(
                        enable_flash=True,
                        enable_math=False,
                        enable_mem_efficient=False,
                    )
            except Exception:
                logger.debug("sdp_kernel not supported, continuing without")
            return

        logger.info("Multi-GPU requested but not available, falling back to single device mode")

    device = get_best_device()

    if memory_optimization_strategy == "Automatic":
        _automatic_optimize_diffusion_pipeline(pipe, device)
    else:
        _manual_optimize_diffusion_pipeline(
            pipe=pipe,
            device=device,
            attention_slicing=attention_slicing,
            vae_slicing=vae_slicing,
            transformer_layerwise_casting=transformer_layerwise_casting,
            cpu_offload_strategy=cpu_offload_strategy,
            quantization_mode=quantization_mode,
        )

    try:
        torch.backends.cuda.matmul.allow_tf32 = True
        if hasattr(torch.backends.cuda, "sdp_kernel"):
            torch.backends.cuda.sdp_kernel(
                enable_flash=True,
                enable_math=False,
                enable_mem_efficient=False,
            )
    except Exception:
        logger.debug("sdp_kernel not supported, continuing without")


def clear_diffusion_pipeline(
    pipe: DiffusionPipeline,
) -> None:
    """Clear pipeline from memory."""
    for component_name in get_pipeline_component_names(pipe):
        if hasattr(pipe, component_name):
            component = getattr(pipe, component_name)
            if component is not None:
                with contextlib.suppress(NotImplementedError):
                    component.to("cpu")
                del component
                setattr(pipe, component_name, None)

    del pipe

    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
