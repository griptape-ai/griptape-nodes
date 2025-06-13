import logging
from functools import cache

import diffusers  # type: ignore[reportMissingImports]
import torch  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.utils.torch_utils import (  # type: ignore[reportMissingImports]
    print_pipeline_memory_footprint,
)

logger = logging.getLogger("diffusers_nodes_library")


def print_controlnet_pipeline_memory_footprint(pipe: diffusers.StableDiffusionControlNetPipeline) -> None:
    """Print pipeline memory footprint."""
    print_pipeline_memory_footprint(
        pipe,
        [
            "vae",
            "text_encoder",
            "unet",
            "controlnet",
        ],
    )


@cache
def optimize_controlnet_pipeline_memory_footprint(pipe: diffusers.StableDiffusionControlNetPipeline) -> None:
    """Optimize ControlNet pipeline memory footprint by moving to GPU.

    Args:
        pipe: The ControlNet pipeline to optimize

    Raises:
        RuntimeError: If CUDA is not available
    """
    if not torch.cuda.is_available():
        msg = "CUDA is required for ControlNet pipeline optimization"
        raise RuntimeError(msg)

    device = "cuda"
    logger.info("Moving ControlNet pipeline to %s", device)
    pipe.to(device)
