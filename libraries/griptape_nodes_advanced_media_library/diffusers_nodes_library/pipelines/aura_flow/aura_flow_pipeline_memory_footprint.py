import functools
import logging

import diffusers  # type: ignore[reportMissingImports]
import torch  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.utils.torch_utils import (
    print_pipeline_memory_footprint,  # type: ignore[reportMissingImports]
)

logger = logging.getLogger("diffusers_nodes_library")


@functools.cache
def optimize_aura_flow_pipeline_memory_footprint(pipe: diffusers.AuraFlowPipeline) -> None:
    """Optimize AuraFlow pipeline memory footprint by moving to GPU.

    Args:
        pipe: The AuraFlow pipeline to optimize

    Raises:
        RuntimeError: If CUDA is not available
    """
    if not torch.cuda.is_available():
        msg = "CUDA is required for AuraFlow pipeline optimization"
        raise RuntimeError(msg)

    device = "cuda"
    logger.info("Moving AuraFlow pipeline to %s", device)
    pipe.to(device)


def print_aura_flow_pipeline_memory_footprint(pipe: diffusers.AuraFlowPipeline) -> None:
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
