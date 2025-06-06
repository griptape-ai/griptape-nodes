import functools
import logging

import diffusers  # type: ignore[reportMissingImports]
import torch  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.utils.torch_utils import get_torch_device  # type: ignore[reportMissingImports]
from diffusers_nodes_library.common.utils.logging_utils import print_pipeline_memory_footprint  # type: ignore[reportMissingImports]

logger = logging.getLogger("diffusers_nodes_library")


@functools.cache
def optimize_sana_pipeline_memory_footprint(pipe: diffusers.SanaPipeline) -> None:
    """Optimize SANA pipeline memory usage for CUDA."""
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is not available. Memory optimization requires CUDA.")
    
    device = get_torch_device()
    pipe.to(device)
    
    # Move text encoder to bfloat16 for efficiency as recommended in docs
    if hasattr(pipe, 'text_encoder') and pipe.text_encoder is not None:
        pipe.text_encoder.to(torch.bfloat16)
    
    # Move transformer to bfloat16 for efficiency
    if hasattr(pipe, 'transformer') and pipe.transformer is not None:
        pipe.transformer = pipe.transformer.to(torch.bfloat16)
    
    logger.info("SANA pipeline moved to CUDA device with optimized precision")


def print_sana_pipeline_memory_footprint(pipe: diffusers.SanaPipeline) -> None:
    """Print memory footprint of SANA pipeline components."""
    components = [
        "vae",
        "text_encoder",
        "transformer",
        "scheduler",
    ]
    print_pipeline_memory_footprint(pipe, components)