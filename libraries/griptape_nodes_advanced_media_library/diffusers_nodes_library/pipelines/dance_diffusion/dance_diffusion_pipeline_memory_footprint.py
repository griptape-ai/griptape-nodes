import logging
from functools import cache

import diffusers  # type: ignore[reportMissingImports]
import torch  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.utils.torch_utils import (  # type: ignore[reportMissingImports]
    print_pipeline_memory_footprint,
)

logger = logging.getLogger("diffusers_nodes_library")


def print_dance_diffusion_pipeline_memory_footprint(pipe: diffusers.DanceDiffusionPipeline) -> None:
    """Print pipeline memory footprint."""
    print_pipeline_memory_footprint(
        pipe,
        [
            "unet",
            "scheduler",
        ],
    )


@cache
def optimize_dance_diffusion_pipeline_memory_footprint(pipe: diffusers.DanceDiffusionPipeline) -> None:
    """Optimize Dance Diffusion pipeline memory footprint by moving to GPU.

    Args:
        pipe: The Dance Diffusion pipeline to optimize

    Raises:
        RuntimeError: If CUDA is not available
    """
    if not torch.cuda.is_available():
        msg = "CUDA is required for Dance Diffusion pipeline optimization"
        raise RuntimeError(msg)

    device = "cuda"
    logger.info("Moving Dance Diffusion pipeline to %s", device)
    pipe.to(device)
