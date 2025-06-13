import functools

import diffusers  # type: ignore[reportMissingImports]
import torch  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.utils.torch_utils import (
    print_pipeline_memory_footprint,  # type: ignore[reportMissingImports]
)


@functools.cache
def optimize_easyanimate_pipeline_memory_footprint(pipe: diffusers.EasyAnimatePipeline) -> None:
    """Optimize EasyAnimate pipeline memory footprint by moving to GPU.

    Args:
        pipe: The EasyAnimate pipeline to optimize

    Raises:
        RuntimeError: If CUDA is not available
    """
    if not torch.cuda.is_available():
        msg = "CUDA is required for EasyAnimate pipeline optimization"
        raise RuntimeError(msg)

    pipe.to("cuda")


def print_easyanimate_pipeline_memory_footprint(pipe: diffusers.EasyAnimatePipeline) -> None:
    """Print memory footprint information for EasyAnimate pipeline components.

    Args:
        pipe: The EasyAnimate pipeline to analyze
    """
    print_pipeline_memory_footprint(
        pipe,
        ["transformer", "text_encoder", "tokenizer", "vae", "scheduler"],
    )
