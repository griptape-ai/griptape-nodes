import functools
import logging

import diffusers  # type: ignore[reportMissingImports]
import torch  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.utils.torch_utils import (
    print_pipeline_memory_footprint,  # type: ignore[reportMissingImports]
)

logger = logging.getLogger("diffusers_nodes_library")


@functools.cache
def optimize_blip_diffusion_pipeline_memory_footprint(pipe: diffusers.BlipDiffusionPipeline) -> None:
    """Optimize BLIP-Diffusion pipeline memory footprint by moving to GPU.

    Args:
        pipe: The BLIP-Diffusion pipeline to optimize

    Raises:
        RuntimeError: If CUDA is not available
    """
    if not torch.cuda.is_available():
        msg = "CUDA is required for BLIP-Diffusion pipeline optimization"
        raise RuntimeError(msg)

    device = "cuda"
    logger.info("Moving BLIP-Diffusion pipeline to %s", device)
    pipe.to(device)


def print_blip_diffusion_pipeline_memory_footprint(pipe: diffusers.BlipDiffusionPipeline) -> None:
    """Print memory footprint information for BLIP-Diffusion pipeline components.

    Args:
        pipe: The BLIP-Diffusion pipeline to analyze
    """
    components_to_analyze = [
        "vae",
        "text_encoder",
        "unet",
        "qformer",
        "blip",
    ]

    print_pipeline_memory_footprint(pipe, components_to_analyze)
