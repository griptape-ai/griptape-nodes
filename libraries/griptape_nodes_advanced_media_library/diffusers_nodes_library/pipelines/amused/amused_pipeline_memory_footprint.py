import logging
from functools import cache

import diffusers  # type: ignore[reportMissingImports]
import torch  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.utils.torch_utils import (
    get_best_device,  # type: ignore[reportMissingImports]
    print_pipeline_memory_footprint,  # type: ignore[reportMissingImports]
)

logger = logging.getLogger("diffusers_nodes_library")


def print_amused_pipeline_memory_footprint(
    pipe: diffusers.AmusedPipeline
    | diffusers.AmusedImg2ImgPipeline
    | diffusers.AmusedInpaintPipeline,  # type: ignore[reportMissingImports]
) -> None:
    """Pretty-print memory footprint for the main sub-modules of Amused pipelines."""
    print_pipeline_memory_footprint(
        pipe,
        [
            "vqvae",
            "text_encoder",
            "transformer",
        ],
    )


@cache  # noqa: B019
def optimize_amused_pipeline_memory_footprint(
    pipe: diffusers.AmusedPipeline
    | diffusers.AmusedImg2ImgPipeline
    | diffusers.AmusedInpaintPipeline,  # type: ignore[reportMissingImports]
) -> None:
    """Apply a basic set of heuristics to reduce VRAM / RAM usage during inference.
    
    Raises:
        RuntimeError: If CUDA is not available.
    """
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is not available")
    
    device = get_best_device()

    if device == torch.device("cuda"):
        logger.info("Enabling sequential CPU offload for CUDA device")
        pipe.enable_sequential_cpu_offload()
    else:
        logger.info("Moving pipeline to device %s", device)
        pipe.to(device)

    # Attention slicing generally helps on constrained hardware.
    logger.info("Enabling attention slicing")
    pipe.enable_attention_slicing()

    logger.info("Final memory footprint:")
    print_amused_pipeline_memory_footprint(pipe) 