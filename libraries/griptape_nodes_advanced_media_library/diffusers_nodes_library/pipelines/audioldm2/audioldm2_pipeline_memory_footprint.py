import functools
import logging

import diffusers  # type: ignore[reportMissingImports]
import torch  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.utils.torch_utils import (
    print_pipeline_memory_footprint,  # type: ignore[reportMissingImports]
)

logger = logging.getLogger("diffusers_nodes_library")


@functools.cache
def optimize_audioldm2_pipeline_memory_footprint(pipe: diffusers.AudioLDM2Pipeline) -> None:
    """Optimize AudioLDM2 pipeline memory footprint by moving to GPU.

    Args:
        pipe: The AudioLDM2 pipeline to optimize

    Raises:
        RuntimeError: If CUDA is not available
    """
    if not torch.cuda.is_available():
        msg = "CUDA is required for AudioLDM2 pipeline optimization"
        raise RuntimeError(msg)

    device = "cuda"
    logger.info("Moving AudioLDM2 pipeline to %s", device)
    pipe.to(device)


def print_audioldm2_pipeline_memory_footprint(pipe: diffusers.AudioLDM2Pipeline) -> None:
    """Print memory footprint information for AudioLDM2 pipeline components.

    Args:
        pipe: The AudioLDM2 pipeline to analyze
    """
    components_to_analyze = [
        "vae",
        "text_encoder",
        "unet",
        "vocoder",
        "projection_model",
    ]

    print_pipeline_memory_footprint(pipe, components_to_analyze)
