import functools
import logging

import diffusers  # type: ignore[reportMissingImports]
import torch  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.utils.torch_utils import print_pipeline_memory_footprint  # type: ignore[reportMissingImports]

logger = logging.getLogger("diffusers_nodes_library")


@functools.cache
def optimize_consistency_models_pipeline_memory_footprint(pipe: diffusers.ConsistencyModelPipeline) -> None:
    """Optimize Consistency Models pipeline memory footprint for CUDA."""
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is not available. Memory optimization requires CUDA.")
    
    logger.info("Optimizing Consistency Models pipeline memory footprint")
    device = torch.device("cuda")
    pipe = pipe.to(device)
    
    # Enable memory optimizations if available
    if hasattr(pipe, 'enable_model_cpu_offload'):
        pipe.enable_model_cpu_offload()


def print_consistency_models_pipeline_memory_footprint(pipe: diffusers.ConsistencyModelPipeline) -> None:
    """Print memory footprint of Consistency Models pipeline components."""
    sub_modules = ["unet", "scheduler"]
    print_pipeline_memory_footprint(pipe, sub_modules)