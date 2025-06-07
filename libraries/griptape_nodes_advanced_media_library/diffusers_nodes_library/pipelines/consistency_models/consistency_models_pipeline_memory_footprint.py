import functools
import logging

import diffusers  # type: ignore[reportMissingImports]
import torch  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.utils.torch_utils import (
    print_pipeline_memory_footprint,  # type: ignore[reportMissingImports]
)

logger = logging.getLogger("diffusers_nodes_library")


@functools.cache
def optimize_consistency_models_pipeline_memory_footprint(pipe: diffusers.ConsistencyModelPipeline) -> None:
    """Optimize Consistency Models pipeline memory footprint for CUDA."""
    if not torch.cuda.is_available():
        msg = "CUDA is not available. Memory optimization requires CUDA."
        raise RuntimeError(msg)

    device = "cuda"
    logger.info("Moving Consistency Models pipeline to %s", device)
    pipe.to(device)


def print_consistency_models_pipeline_memory_footprint(pipe: diffusers.ConsistencyModelPipeline) -> None:
    """Print memory footprint of Consistency Models pipeline components."""
    sub_modules = ["unet", "scheduler"]
    print_pipeline_memory_footprint(pipe, sub_modules)
