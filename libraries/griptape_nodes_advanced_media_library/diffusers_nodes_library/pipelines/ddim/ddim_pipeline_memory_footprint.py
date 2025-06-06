import functools
import logging

import torch  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.utils.logging_utils import print_pipeline_memory_footprint  # type: ignore[reportMissingImports]

logger = logging.getLogger("diffusers_nodes_library")


@functools.cache
def optimize_ddim_pipeline_memory_footprint(pipe) -> None:
    """Optimize DDIM pipeline memory footprint by moving to GPU.
    
    Args:
        pipe: The DDIM pipeline to optimize
        
    Raises:
        RuntimeError: If CUDA is not available
    """
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is required for DDIM pipeline optimization")
    
    device = "cuda"
    logger.info(f"Moving DDIM pipeline to {device}")
    pipe.to(device)


def print_ddim_pipeline_memory_footprint(pipe) -> None:
    """Print memory footprint information for DDIM pipeline components.
    
    Args:
        pipe: The DDIM pipeline to analyze
    """
    components_to_analyze = [
        "unet",
        "scheduler",
    ]
    
    print_pipeline_memory_footprint(pipe, components_to_analyze)