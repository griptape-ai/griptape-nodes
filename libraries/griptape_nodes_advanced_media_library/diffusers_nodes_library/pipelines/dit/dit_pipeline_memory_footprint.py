import functools

import torch  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.utils.torch_utils import print_pipeline_memory_footprint  # type: ignore[reportMissingImports]


@functools.cache
def optimize_dit_pipeline_memory_footprint(pipe) -> None:
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is required for DiT pipeline optimization")
    
    pipe.to("cuda")


def print_dit_pipeline_memory_footprint(pipe) -> None:
    print_pipeline_memory_footprint(
        pipe,
        [
            "transformer",
            "vae",
            "scheduler"
        ],
    )