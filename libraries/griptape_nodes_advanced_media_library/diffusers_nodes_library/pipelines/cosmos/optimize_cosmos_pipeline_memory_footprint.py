import logging
from functools import cache

import diffusers  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.utils.torch_utils import (
    get_best_device,
)
from diffusers_nodes_library.pipelines.cosmos.print_cosmos_pipeline_memory_footprint import (
    print_cosmos_pipeline_memory_footprint,
)

logger = logging.getLogger("diffusers_nodes_library")


@cache
def optimize_cosmos_pipeline_memory_footprint(pipe) -> None:
    """Apply a minimal set of optimisations and move the pipeline to the best device.

    For the initial release we keep things intentionally simple and conservative – just enable
    attention slicing when it makes sense and move the whole pipeline to the device selected
    by `get_best_device`. Additional optimisations (e.g. layer-wise casting or sequential CPU
    offload) can be added later based on profiling results.
    
    Args:
        pipe: The Cosmos pipeline (type annotation omitted for compatibility)
    """
    device = get_best_device()

    # Move to device early so that subsequent calls use the correct default device.
    logger.info("Transferring Cosmos pipeline to %s", device)
    pipe.to(device)

    # Enable attention slicing on memory-constrained devices.
    if device.type in {"cpu", "mps"}:
        logger.info("Enabling attention slicing for Cosmos pipeline")
        if hasattr(pipe, 'enable_attention_slicing'):
            pipe.enable_attention_slicing()

    # Final footprint printout for debugging purposes.
    logger.info("Final Cosmos memory footprint:")
    print_cosmos_pipeline_memory_footprint(pipe)