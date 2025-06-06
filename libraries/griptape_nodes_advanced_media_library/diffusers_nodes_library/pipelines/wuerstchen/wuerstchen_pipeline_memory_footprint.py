import logging
from functools import cache

import diffusers  # type: ignore[reportMissingImports]
import torch  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.utils.torch_utils import (  # type: ignore[reportMissingImports]
    get_best_device,
    print_pipeline_memory_footprint,
)

logger = logging.getLogger("diffusers_nodes_library")


def print_wuerstchen_pipeline_memory_footprint(pipe: diffusers.WuerstchenCombinedPipeline) -> None:
    """Print pipeline memory footprint."""
    print_pipeline_memory_footprint(
        pipe,
        [
            "vqgan",
            "decoder",
            "prior_prior",
            "prior_text_encoder",
        ],
    )


@cache
def optimize_wuerstchen_pipeline_memory_footprint(pipe: diffusers.WuerstchenCombinedPipeline) -> None:
    """Optimize pipeline memory footprint."""
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is required for Wuerstchen pipeline optimization")
    
    device = get_best_device()

    if device == torch.device("cuda"):
        # We specifically do not call pipe.to(device) for gpus
        # because it would move ALL the models in the pipe to the
        # gpus, potentially causing us to exhaust available VRAM,
        # and essentially undo all of the following VRAM pressure
        # reducing optimizations in vain.
        #
        # TL;DR - DONT CALL `pipe.to(device)` FOR GPUS!
        # (unless you checked pipe is small enough!)

        # Sequential cpu offload only makes sense for gpus (VRAM <-> RAM).
        logger.info("Enabling sequential cpu offload")
        pipe.enable_sequential_cpu_offload()
    
    # Enable attention slicing for memory efficiency
    logger.info("Enabling attention slicing")
    pipe.enable_attention_slicing()
    
    # Enable VAE slicing if available
    if hasattr(pipe, "enable_vae_slicing"):
        logger.info("Enabling vae slicing")
        pipe.enable_vae_slicing()
    elif hasattr(pipe, "vqgan") and hasattr(pipe.vqgan, "enable_slicing"):
        logger.info("Enabling vqgan slicing")
        pipe.vqgan.enable_slicing()

    logger.info("Final memory footprint:")
    print_wuerstchen_pipeline_memory_footprint(pipe)

    if device == torch.device("mps"):
        # You must move the pipeline models to MPS if available to
        # use it (otherwise you'll get the CPU).
        logger.info("Transferring model to MPS/GPU - may take minutes")
        pipe.to(device)

    if device == torch.device("cuda"):
        # We specifically do not call pipe.to(device) for gpus
        # because it would move ALL the models in the pipe to the
        # gpus, potentially causing us to exhaust available VRAM,
        # and essentially undo all of the following VRAM pressure
        # reducing optimizations in vain.
        #
        # TL;DR - DONT CALL `pipe.to(device)` FOR GPUS!
        # (unless you checked pipe is small enough!)
        pass