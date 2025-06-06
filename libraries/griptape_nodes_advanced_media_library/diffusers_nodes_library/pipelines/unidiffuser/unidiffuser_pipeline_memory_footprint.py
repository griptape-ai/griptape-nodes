import logging
from functools import cache

import diffusers  # type: ignore[reportMissingImports]
import torch  # type: ignore[reportMissingImports]
import torch.nn.functional  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.utils.torch_utils import (  # type: ignore[reportMissingImports]
    get_best_device,
    print_pipeline_memory_footprint,
)

logger = logging.getLogger("diffusers_nodes_library")


def print_unidiffuser_pipeline_memory_footprint(pipe: diffusers.UniDiffuserPipeline) -> None:
    """Print pipeline memory footprint."""
    print_pipeline_memory_footprint(
        pipe,
        [
            "vae",
            "text_encoder",
            "image_encoder",
            "unet",
        ],
    )


@cache
def optimize_unidiffuser_pipeline_memory_footprint(pipe: diffusers.UniDiffuserPipeline) -> None:
    """Optimize pipeline memory footprint."""
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is not available. UniDiffuser requires GPU acceleration.")
    
    device = get_best_device()

    if device == torch.device("cuda"):
        # Sequential cpu offload only makes sense for gpus (VRAM <-> RAM).
        logger.info("Enabling sequential cpu offload")
        pipe.enable_sequential_cpu_offload()
    
    # Enable memory efficient attention
    logger.info("Enabling attention slicing")
    pipe.enable_attention_slicing()
    
    # Enable VAE slicing if available
    if hasattr(pipe, "enable_vae_slicing"):
        logger.info("Enabling vae slicing")
        pipe.enable_vae_slicing()
    elif hasattr(pipe, "vae") and hasattr(pipe.vae, "enable_slicing"):
        logger.info("Enabling vae slicing")
        pipe.vae.enable_slicing()

    logger.info("Final memory footprint:")
    print_unidiffuser_pipeline_memory_footprint(pipe)

    if device == torch.device("mps"):
        # You must move the pipeline models to MPS if available to
        # use it (otherwise you'll get the CPU).
        logger.info("Transferring model to MPS/GPU - may take minutes")
        pipe.to(device)

    if device == torch.device("cuda"):
        # For UniDiffuser, we use sequential cpu offload
        # which manages GPU memory more efficiently for large models
        pass