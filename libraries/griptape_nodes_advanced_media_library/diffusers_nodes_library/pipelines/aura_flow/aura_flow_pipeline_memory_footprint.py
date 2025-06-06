import functools
import logging

import torch  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.utils.logging_utils import print_pipeline_memory_footprint  # type: ignore[reportMissingImports]

logger = logging.getLogger("diffusers_nodes_library")


@functools.cache
def optimize_aura_flow_pipeline_memory_footprint(pipe) -> None:
    """Optimize AuraFlow pipeline memory footprint by moving to GPU.
    
    Args:
        pipe: The AuraFlow pipeline to optimize
        
    Raises:
        RuntimeError: If CUDA is not available
    """
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is required for AuraFlow pipeline optimization")
    
    device = "cuda"
    logger.info(f"Moving AuraFlow pipeline to {device}")
    pipe.to(device)


def print_aura_flow_pipeline_memory_footprint(pipe) -> None:
    """Print memory footprint information for AuraFlow pipeline components.
    
    Args:
        pipe: The AuraFlow pipeline to analyze
    """
    components_to_analyze = [
        "transformer",
        "vae",
        "text_encoder",
    ]
    
    print_pipeline_memory_footprint(pipe, components_to_analyze)