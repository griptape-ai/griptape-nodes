import functools

import diffusers  # type: ignore[reportMissingImports]
import torch  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.utils.torch_utils import (
    print_pipeline_memory_footprint,  # type: ignore[reportMissingImports]
)


@functools.cache
def optimize_dit_pipeline_memory_footprint(pipe: diffusers.DiTPipeline) -> None:
    """Optimize DiT pipeline memory footprint by moving to GPU.

    Args:
        pipe: The DiT pipeline to optimize

    Raises:
        RuntimeError: If CUDA is not available
    """
    if not torch.cuda.is_available():
        msg = "CUDA is required for DiT pipeline optimization"
        raise RuntimeError(msg)

    pipe.to("cuda")


def print_dit_pipeline_memory_footprint(pipe: diffusers.DiTPipeline) -> None:
    """Print memory footprint information for DiT pipeline components.

    Args:
        pipe: The DiT pipeline to analyze
    """
    print_pipeline_memory_footprint(
        pipe,
        ["transformer", "vae", "scheduler"],
    )
