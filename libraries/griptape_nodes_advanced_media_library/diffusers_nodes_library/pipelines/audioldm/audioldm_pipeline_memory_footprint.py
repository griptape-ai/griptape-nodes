import functools
import logging

import torch  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.utils.logging_utils import print_pipeline_memory_footprint  # type: ignore[reportMissingImports]

logger = logging.getLogger("diffusers_nodes_library")


@functools.cache
def optimize_audioldm_pipeline_memory_footprint(pipe) -> None:
    """Optimize AudioLDM pipeline memory footprint by moving to GPU.
    
    Args:
        pipe: The AudioLDM pipeline to optimize
        
    Raises:
        RuntimeError: If CUDA is not available
    """
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is required for AudioLDM pipeline optimization")
    
    device = "cuda"
    logger.info(f"Moving AudioLDM pipeline to {device}")
    pipe.to(device)


def print_audioldm_pipeline_memory_footprint(pipe) -> None:
    """Print memory footprint information for AudioLDM pipeline components.
    
    Args:
        pipe: The AudioLDM pipeline to analyze
    """
    components_to_analyze = [
        "vae",
        "text_encoder", 
        "unet",
        "vocoder",
    ]
    
    print_pipeline_memory_footprint(pipe, components_to_analyze)