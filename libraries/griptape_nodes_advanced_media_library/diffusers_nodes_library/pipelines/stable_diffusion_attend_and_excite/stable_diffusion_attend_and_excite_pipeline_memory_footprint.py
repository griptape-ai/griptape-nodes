import logging
from functools import cache

import diffusers  # type: ignore[reportMissingImports]
import torch  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.utils.torch_utils import (  # type: ignore[reportMissingImports]
    get_best_device,
    print_pipeline_memory_footprint,
)

logger = logging.getLogger("diffusers_nodes_library")


def print_stable_diffusion_attend_and_excite_pipeline_memory_footprint(
    pipe: diffusers.StableDiffusionAttendAndExcitePipeline,
) -> None:
    """Print pipeline memory footprint."""
    print_pipeline_memory_footprint(
        pipe,
        [
            "vae",
            "text_encoder",
            "unet",
            "safety_checker",
        ],
    )


@cache
def optimize_stable_diffusion_attend_and_excite_pipeline_memory_footprint(
    pipe: diffusers.StableDiffusionAttendAndExcitePipeline,
) -> None:
    """Optimize pipeline memory footprint."""
    device = get_best_device()

    if not torch.cuda.is_available():
        msg = "CUDA is required for optimization but is not available"
        raise RuntimeError(msg)

    if device == torch.device("cuda"):
        logger.info("Enabling sequential cpu offload")
        pipe.enable_sequential_cpu_offload()

    logger.info("Enabling attention slicing")
    pipe.enable_attention_slicing()

    if hasattr(pipe, "enable_vae_slicing"):
        logger.info("Enabling vae slicing")
        pipe.enable_vae_slicing()
    elif hasattr(pipe, "vae"):
        logger.info("Enabling vae slicing")
        pipe.vae.enable_slicing()

    logger.info("Final memory footprint:")
    print_stable_diffusion_attend_and_excite_pipeline_memory_footprint(pipe)

    if device == torch.device("mps"):
        logger.info("Transferring model to MPS/GPU - may take minutes")
        pipe.to(device)
