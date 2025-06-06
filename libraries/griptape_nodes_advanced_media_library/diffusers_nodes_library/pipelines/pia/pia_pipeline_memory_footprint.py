import functools
import logging

import diffusers  # type: ignore[reportMissingImports]
import torch  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.utils.torch_utils import get_torch_device  # type: ignore[reportMissingImports]
from diffusers_nodes_library.common.utils.logging_utils import print_pipeline_memory_footprint  # type: ignore[reportMissingImports]

logger = logging.getLogger("diffusers_nodes_library")


@functools.cache
def optimize_pia_pipeline_memory_footprint(pipe: diffusers.PIAPipeline) -> None:
    """Optimize PIA pipeline memory usage for CUDA."""
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is not available. Memory optimization requires CUDA.")
    
    device = get_torch_device()
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