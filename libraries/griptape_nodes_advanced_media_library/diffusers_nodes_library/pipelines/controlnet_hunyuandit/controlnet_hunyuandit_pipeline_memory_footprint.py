import logging
from functools import cache

import diffusers  # type: ignore[reportMissingImports]
import torch  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.utils.torch_utils import (  # type: ignore[reportMissingImports]
    print_pipeline_memory_footprint,
)

logger = logging.getLogger("diffusers_nodes_library")


def print_controlnet_hunyuandit_pipeline_memory_footprint(pipe: diffusers.HunyuanDiTControlNetPipeline) -> None:
    """Print pipeline memory footprint."""
    print_pipeline_memory_footprint(
        pipe,
        [
            "vae",
            "text_encoder",
            "text_encoder_2",
            "transformer",
            "controlnet",
        ],
    )


@cache
def optimize_controlnet_hunyuandit_pipeline_memory_footprint(pipe: diffusers.HunyuanDiTControlNetPipeline) -> None:
    """Optimize ControlNet HunyuanDiT pipeline memory footprint by moving to GPU.

    Args:
        pipe: The ControlNet HunyuanDiT pipeline to optimize

    Raises:
        RuntimeError: If CUDA is not available
    """
    if not torch.cuda.is_available():
        msg = "CUDA is required for ControlNet HunyuanDiT pipeline optimization"
        raise RuntimeError(msg)

    device = "cuda"
    logger.info("Moving ControlNet HunyuanDiT pipeline to %s", device)
    pipe.to(device)
