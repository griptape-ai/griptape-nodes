import functools
import logging

import diffusers  # type: ignore[reportMissingImports]
import torch  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.utils.torch_utils import (
    get_best_device,  # type: ignore[reportMissingImports]
    print_pipeline_memory_footprint,  # type: ignore[reportMissingImports]
)

logger = logging.getLogger("diffusers_nodes_library")


@functools.cache
def optimize_pia_pipeline_memory_footprint(pipe: diffusers.PIAPipeline) -> None:
    """Optimize PIA pipeline memory usage for CUDA."""
    if not torch.cuda.is_available():
        msg = "CUDA is not available. Memory optimization requires CUDA."
        raise RuntimeError(msg)

    device = get_best_device()
    pipe.to(device)
    logger.info("PIA pipeline moved to CUDA device")


def print_pia_pipeline_memory_footprint(pipe: diffusers.PIAPipeline) -> None:
    """Print memory footprint of PIA pipeline components."""
    components = [
        "vae",
        "unet",
        "motion_adapter",
        "scheduler",
    ]
    print_pipeline_memory_footprint(pipe, components)
