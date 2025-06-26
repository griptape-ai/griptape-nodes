import logging
from functools import cache

import diffusers  # type: ignore[reportMissingImports]
import torch  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.utils.torch_utils import (
    get_best_device,
    get_total_memory_footprint,  # type: ignore[reportMissingImports]
    print_pipeline_memory_footprint,
    to_human_readable_size,  # type: ignore[reportMissingImports]
)

logger = logging.getLogger("diffusers_nodes_library")


FLUX_KONTEXT_PIPELINE_COMPONENT_NAMES = [
    "vae",
    "text_encoder",
    "text_encoder_2",
    "transformer",
]


def print_flux_kontext_pipeline_memory_footprint(pipe: diffusers.FluxKontextPipeline) -> None:
    """Print memory footprint for the main sub-modules of Flux Kontext pipelines."""
    print_pipeline_memory_footprint(pipe, FLUX_KONTEXT_PIPELINE_COMPONENT_NAMES)


def _check_cuda_memory_sufficient(pipe: diffusers.FluxKontextPipeline, device: torch.device) -> bool:
    """Check if CUDA device has sufficient memory for the pipeline."""
    model_memory = get_total_memory_footprint(pipe, FLUX_KONTEXT_PIPELINE_COMPONENT_NAMES)
    total_memory = torch.cuda.get_device_properties(device).total_memory
    free_memory = total_memory - torch.cuda.memory_allocated(device)
    return model_memory <= free_memory


def _check_mps_memory_sufficient(pipe: diffusers.FluxKontextPipeline) -> bool:
    """Check if MPS device has sufficient memory for the pipeline."""
    model_memory = get_total_memory_footprint(pipe, FLUX_KONTEXT_PIPELINE_COMPONENT_NAMES)
    recommended_max_memory = torch.mps.recommended_max_memory()
    free_memory = recommended_max_memory - torch.mps.current_allocated_memory()
    return model_memory <= free_memory


def _log_memory_info(pipe: diffusers.FluxKontextPipeline, device: torch.device) -> None:
    """Log memory information for the device."""
    model_memory = get_total_memory_footprint(pipe, FLUX_KONTEXT_PIPELINE_COMPONENT_NAMES)

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

    logger.info("Require memory for Flux Kontext Pipeline: %s", to_human_readable_size(model_memory))


@cache
def optimize_flux_kontext_pipeline_memory_footprint(pipe: diffusers.FluxKontextPipeline) -> None:
    """Optimize pipeline memory footprint with incremental VRAM checking."""
    device = get_best_device()

    if device.type == "cuda":
        _log_memory_info(pipe, device)

        if _check_cuda_memory_sufficient(pipe, device):
            logger.info("Sufficient memory on %s for Pipeline.", device)
            logger.info("Moving pipeline to %s", device)
            pipe.to(device)
            return

        logger.warning("Insufficient memory on %s for Pipeline. Applying VRAM optimizations.", device)

        # Apply fp8 layerwise caching
        logger.info("Enabling fp8 layerwise caching for transformer")
        pipe.transformer.enable_layerwise_casting(
            storage_dtype=torch.float8_e4m3fn,
            compute_dtype=torch.bfloat16,
        )

        if _check_cuda_memory_sufficient(pipe, device):
            logger.info("Sufficient memory after fp8 optimization. Moving pipeline to %s", device)
            pipe.to(device)
            return

        # Apply sequential CPU offload
        logger.info("Still insufficient memory. Enabling sequential cpu offload")
        pipe.enable_sequential_cpu_offload()

        if _check_cuda_memory_sufficient(pipe, device):
            logger.info("Sufficient memory after sequential cpu offload")
            return

        # Apply VAE slicing as final optimization
        logger.info("Enabling vae slicing")
        pipe.enable_vae_slicing()

        # Final check after all optimizations
        if not _check_cuda_memory_sufficient(pipe, device):
            logger.warning("Memory may still be insufficient after all optimizations, but will try anyway")

        # Intentionally not calling pipe.to(device) here because sequential_cpu_offload
        # manages device placement automatically

    elif device.type == "mps":
        _log_memory_info(pipe, device)

        if _check_mps_memory_sufficient(pipe):
            logger.info("Sufficient memory on %s for Pipeline.", device)
            logger.info("Moving pipeline to %s", device)
            pipe.to(device)
            return

        logger.warning("Insufficient memory on %s for Pipeline.", device)
        logger.info("Enabling vae slicing")
        pipe.enable_vae_slicing()

        # Final check after VAE slicing
        if not _check_mps_memory_sufficient(pipe):
            logger.warning("Memory may still be insufficient after optimizations, but will try anyway")

        # Intentionally not calling pipe.to(device) here when memory is insufficient
        # to avoid potential OOM errors
