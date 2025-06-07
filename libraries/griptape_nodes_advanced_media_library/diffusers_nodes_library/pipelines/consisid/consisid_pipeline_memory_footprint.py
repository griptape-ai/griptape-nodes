import functools
import logging

import diffusers  # type: ignore[reportMissingImports]
import torch  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.utils.torch_utils import (
    print_pipeline_memory_footprint,  # type: ignore[reportMissingImports]
)

logger = logging.getLogger("diffusers_nodes_library")


@functools.cache
def optimize_consisid_pipeline_memory_footprint(pipe: diffusers.ConsisIDPipeline) -> None:
    """Optimize ConsisID pipeline memory footprint for CUDA."""
    if not torch.cuda.is_available():
        msg = "CUDA is not available. Memory optimization requires CUDA."
        raise RuntimeError(msg)

    device = "cuda"
    logger.info("Moving ConsisID pipeline to %s", device)
    pipe.to(device)


def print_consisid_pipeline_memory_footprint(pipe: diffusers.ConsisIDPipeline) -> None:
    """Print memory footprint of ConsisID pipeline components."""
    sub_modules = ["transformer", "vae", "text_encoder", "face_helper_1", "face_helper_2"]
    print_pipeline_memory_footprint(pipe, sub_modules)
