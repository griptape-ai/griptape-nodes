import logging
from functools import cache

import diffusers  # type: ignore[reportMissingImports]
import torch  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.utils.torch_utils import (  # type: ignore[reportMissingImports]
    get_best_device,
    print_pipeline_memory_footprint,
)

logger = logging.getLogger("diffusers_nodes_library")


@cache
def optimize_allegro_pipeline_memory_footprint(pipe: diffusers.AllegroPipeline) -> None:
    """Apply a minimal set of optimisations and move the pipeline to the best device.

    Raises:
        RuntimeError: If CUDA is not available.
    """
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is not available")
    
    device = get_best_device()

    # Move to device early so that subsequent calls use the correct default device.
    logger.info("Transferring Allegro pipeline to %s", device)
    pipe.to(device)

    # Enable attention slicing on memory-constrained devices.
    if device.type in {"cpu", "mps"}:
        logger.info("Enabling attention slicing for Allegro pipeline")
        pipe.enable_attention_slicing()

    # Final footprint printout for debugging purposes.
    logger.info("Final Allegro memory footprint:")
    print_allegro_pipeline_memory_footprint(pipe)


def print_allegro_pipeline_memory_footprint(pipe: diffusers.AllegroPipeline) -> None:
    """Convenience wrapper around print_pipeline_memory_footprint for Allegro."""
    component_names = [
        "vae",
        "text_encoder",
        "transformer",
    ]
    print_pipeline_memory_footprint(pipe, component_names)