import functools
import logging

import diffusers  # type: ignore[reportMissingImports]
import torch  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.utils.torch_utils import (
    print_pipeline_memory_footprint,  # type: ignore[reportMissingImports]
)

logger = logging.getLogger("diffusers_nodes_library")


@functools.cache
def optimize_cogvideo_pipeline_memory_footprint(pipe: diffusers.CogVideoXPipeline) -> None:
    """Optimize CogVideo pipeline memory footprint by moving to GPU.

    Args:
        pipe: The CogVideo pipeline to optimize

    Raises:
        RuntimeError: If CUDA is not available
    """
    if not torch.cuda.is_available():
        msg = "CUDA is required for CogVideo pipeline optimization"
        raise RuntimeError(msg)

    device = "cuda"
    logger.info("Moving CogVideo pipeline to %s", device)
    pipe.to(device)


def print_cogvideo_pipeline_memory_footprint(pipe: diffusers.CogVideoXPipeline) -> None:
    """Print memory footprint information for CogVideo pipeline components.

    Args:
        pipe: The CogVideo pipeline to analyze
    """
    components_to_analyze = [
        "transformer",
        "vae",
        "text_encoder",
    ]

    print_pipeline_memory_footprint(pipe, components_to_analyze)
