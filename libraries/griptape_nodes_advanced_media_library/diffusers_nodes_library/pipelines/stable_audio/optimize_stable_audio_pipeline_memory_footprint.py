import logging
from functools import cache

import diffusers  # type: ignore[reportMissingImports]
import torch  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.utils.torch_utils import (
    get_best_device,  # type: ignore[reportMissingImports]
    print_pipeline_memory_footprint,  # type: ignore[reportMissingImports]
)

logger = logging.getLogger("diffusers_nodes_library")


def print_stable_audio_pipeline_memory_footprint(
    pipe: diffusers.StableAudioPipeline,  # type: ignore[reportMissingImports]
) -> None:
    """Print memory footprint for the main sub-modules of Stable Audio pipelines."""
    print_pipeline_memory_footprint(
        pipe,
        [
            "text_encoder",
            "unet",
            "vae",
        ],
    )


@cache
def optimize_stable_audio_pipeline_memory_footprint(
    pipe: diffusers.StableAudioPipeline,  # type: ignore[reportMissingImports]
) -> None:
    """Apply a set of heuristics to minimise VRAM / RAM footprint at inference time.

    The logic follows the same rationale as the optimisation helper for other
    pipelines but adapted to the component layout of Stable Audio.
    """
    device = get_best_device()

    if device == torch.device("cuda"):
        # Avoid blindly moving the whole pipeline to CUDA. Instead rely on
        # Diffusers' built-in sequential offload helper which swaps modules
        # between CPU ↔ GPU as needed.
        logger.info("Enabling sequential CPU offload")
        pipe.enable_sequential_cpu_offload()
    else:
        # For MPS / CPU back-ends we *do* need to call .to(device).
        logger.info("Transferring model to %s — may take a while the first time", device)
        pipe.to(device)

    # Attention slicing helps with memory usage.
    logger.info("Enabling attention slicing")
    pipe.enable_attention_slicing()

    # VAE slicing for better memory efficiency.
    if hasattr(pipe, "vae") and hasattr(pipe.vae, "enable_slicing"):
        logger.info("Enabling VAE slicing")
        pipe.vae.enable_slicing()

    logger.info("Final memory footprint:")
    print_stable_audio_pipeline_memory_footprint(pipe)
