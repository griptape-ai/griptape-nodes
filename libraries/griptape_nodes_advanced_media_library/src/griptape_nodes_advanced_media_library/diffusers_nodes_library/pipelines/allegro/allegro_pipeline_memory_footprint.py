import logging
from functools import cache

import diffusers  # type: ignore[reportMissingImports]
import torch  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.utils.torch_utils import (  # type: ignore[reportMissingImports]
    get_best_device,
    get_total_memory_footprint,
    print_pipeline_memory_footprint,
    to_human_readable_size,
)

logger = logging.getLogger("diffusers_nodes_library")

ALLEGRO_PIPELINE_COMPONENT_NAMES = [
    "vae",
    "text_encoder",
    "transformer",
]


@cache
def optimize_allegro_pipeline_memory_footprint(pipe: diffusers.AllegroPipeline) -> None:
    """Apply a minimal set of optimizations and move the pipeline to the best device."""
    device = get_best_device()

    # Move to device early so that subsequent calls use the correct default device.
    logger.info("Transferring pipeline to %s", device)

    model_memory = get_total_memory_footprint(pipe, ALLEGRO_PIPELINE_COMPONENT_NAMES)

    if device.type == "cuda":
        total_memory = torch.cuda.get_device_properties(device).total_memory
        free_memory = total_memory - torch.cuda.memory_allocated(device)
        logger.info("Total memory on %s: %s", device, to_human_readable_size(total_memory))
        logger.info("Free memory on %s: %s", device, to_human_readable_size(free_memory))
        logger.info("Require memory for Pipeline: %s", to_human_readable_size(model_memory))
        if model_memory > free_memory:
            logger.warning(
                "Insufficient memory on %s for Pipeline. Consider using a smaller model or freeing up memory.",
                device,
            )
            msg = f"Insufficient memory on {device} for Pipeline. "
            raise RuntimeError(msg)
        pipe.to(device)
    elif device.type == "mps":
        recommended_max_memory = torch.mps.recommended_max_memory()
        free_memory = recommended_max_memory - torch.mps.current_allocated_memory()
        logger.info("Recommended max memory on %s: %s", device, to_human_readable_size(recommended_max_memory))
        logger.info("Free memory on %s: %s", device, to_human_readable_size(free_memory))
        logger.info("Require memory for Pipeline: %s", to_human_readable_size(model_memory))
        if model_memory > free_memory:
            logger.warning(
                "Insufficient memory on %s for Pipeline. Consider using a smaller model or freeing up memory.",
                device,
            )
            msg = f"Insufficient memory on {device} for Pipeline. "
            raise RuntimeError(msg)
        pipe.to(device)

    # Final footprint printout for debugging purposes.
    logger.info("Final memory footprint:")
    print_allegro_pipeline_memory_footprint(pipe)


def print_allegro_pipeline_memory_footprint(pipe: diffusers.AllegroPipeline) -> None:
    """Convenience wrapper around print_pipeline_memory_footprint for Allegro."""
    print_pipeline_memory_footprint(pipe, ALLEGRO_PIPELINE_COMPONENT_NAMES)
