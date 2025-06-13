import functools
from typing import Any

import torch  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.utils.torch_utils import (
    print_pipeline_memory_footprint,  # type: ignore[reportMissingImports]
)


@functools.cache
def optimize_hidream_image_pipeline_memory_footprint(pipe: Any) -> None:
    """Optimize HiDream Image pipeline memory footprint by moving to GPU.

    Args:
        pipe: The HiDream Image pipeline to optimize

    Raises:
        RuntimeError: If CUDA is not available
    """
    if not torch.cuda.is_available():
        msg = "CUDA is required for HiDream Image pipeline optimization"
        raise RuntimeError(msg)

    pipe.to("cuda")


def print_hidream_image_pipeline_memory_footprint(pipe: Any) -> None:
    """Print memory footprint information for HiDream Image pipeline components.

    Args:
        pipe: The HiDream Image pipeline to analyze
    """
    print_pipeline_memory_footprint(
        pipe,
        ["transformer", "text_encoder", "tokenizer", "vae", "scheduler"],
    )
