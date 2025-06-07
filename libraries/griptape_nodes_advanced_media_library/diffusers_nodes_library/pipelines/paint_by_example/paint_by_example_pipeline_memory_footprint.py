import functools
import logging

import diffusers  # type: ignore[reportMissingImports]
import torch  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.utils.torch_utils import (
    get_best_device,  # type: ignore[reportMissingImports]
    print_pipeline_memory_footprint,  # type: ignore[reportMissingImports]
)

logger = logging.getLogger("diffusers_nodes_library")


@functools.cache
def optimize_paint_by_example_pipeline_memory_footprint(pipe: diffusers.PaintByExamplePipeline) -> None:
    """Optimize PaintByExample pipeline memory usage for CUDA."""
    if not torch.cuda.is_available():
        msg = "CUDA is not available. Memory optimization requires CUDA."
        raise RuntimeError(msg)

    device = get_best_device()
    pipe.to(device)
    logger.info("PaintByExample pipeline moved to CUDA device")


def print_paint_by_example_pipeline_memory_footprint(pipe: diffusers.PaintByExamplePipeline) -> None:
    """Print memory footprint of PaintByExample pipeline components."""
    components = [
        "vae",
        "image_encoder",
        "unet",
        "scheduler",
    ]
    print_pipeline_memory_footprint(pipe, components)
