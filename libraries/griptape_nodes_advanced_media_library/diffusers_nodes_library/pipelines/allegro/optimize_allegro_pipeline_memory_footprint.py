import logging
from functools import cache

import diffusers  # type: ignore[reportMissingImports]
import torch  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.utils.torch_utils import (
    print_pipeline_memory_footprint,  # type: ignore[reportMissingImports]
)

logger = logging.getLogger("diffusers_nodes_library")


def print_allegro_pipeline_memory_footprint(
    pipe: diffusers.AllegroPipeline,  # type: ignore[reportMissingImports]
) -> None:
    """Print the memory footprint of key Allegro components."""
    print_pipeline_memory_footprint(
        pipe,
        [
            "text_encoder",
            "transformer",
            "vae",
        ],
    )


@cache  # noqa: B019
def optimize_allegro_pipeline_memory_footprint(
    pipe: diffusers.AllegroPipeline,  # type: ignore[reportMissingImports]
) -> None:
    """Simplified optimisation: just move the pipeline to the best device per PLAN.md."""

    if not torch.cuda.is_available():
        msg = "CUDA device is required for Allegro optimisation but not available."
        raise RuntimeError(msg)

    device = torch.device("cuda")
    logger.info("Moving Allegro pipeline to CUDA GPU")
    pipe.to(device)

    logger.info("Memory footprint after simple .to(device):")
    print_allegro_pipeline_memory_footprint(pipe) 