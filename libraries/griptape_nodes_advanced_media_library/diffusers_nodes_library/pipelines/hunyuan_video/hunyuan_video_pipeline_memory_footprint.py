import functools
from typing import Any

import torch  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.utils.torch_utils import (
    print_pipeline_memory_footprint,  # type: ignore[reportMissingImports]
)


@functools.cache
def optimize_hunyuan_video_pipeline_memory_footprint(pipe: Any) -> None:
    """Optimize HunyuanVideo pipeline memory footprint for CUDA."""
    if not torch.cuda.is_available():
        msg = "CUDA is required for HunyuanVideo pipeline optimization"
        raise RuntimeError(msg)

    pipe.to("cuda")


def print_hunyuan_video_pipeline_memory_footprint(pipe: Any) -> None:
    """Print HunyuanVideo pipeline memory footprint."""
    print_pipeline_memory_footprint(
        pipe,
        ["transformer", "text_encoder", "text_encoder_2", "tokenizer", "tokenizer_2", "vae", "scheduler"],
    )
