"""Memory footprint estimate for Cosmos pipeline.

This module provides CUDA memory requirements for the Cosmos video generation pipeline.
The pipeline requires significant GPU memory due to the transformer architecture used
for video generation.
"""

import functools
import logging
from typing import Any

import torch  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.utils.torch_utils import (  # type: ignore[reportMissingImports]
    print_pipeline_memory_footprint,
)

logger = logging.getLogger("diffusers_nodes_library")

# Estimated CUDA memory requirements (in GB)
CUDA_MEMORY_REQUIREMENT_GB = 16  # Conservative estimate for video generation


@functools.cache
def optimize_cosmos_pipeline_memory_footprint(pipe: Any) -> None:
    """Optimize the CosmosPipeline for CUDA execution.

    Args:
        pipe: The CosmosPipeline instance to optimize.

    Raises:
        RuntimeError: If CUDA is not available.
    """
    if not torch.cuda.is_available():
        msg = "CUDA is required for CosmosPipeline optimization."
        raise RuntimeError(msg)

    device = torch.device("cuda")
    pipe.to(device)
    logger.info("CosmosPipeline moved to CUDA device.")


def print_cosmos_pipeline_memory_footprint(pipe: Any) -> None:
    """Print memory footprint information for the CosmosPipeline.

    Args:
        pipe: The CosmosPipeline instance to analyze.
    """
    # Key components of the Cosmos pipeline
    component_names = ["text_encoder", "transformer", "vae", "scheduler"]

    print_pipeline_memory_footprint(pipe, component_names)
