import functools

import torch  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.utils.torch_utils import print_pipeline_memory_footprint  # type: ignore[reportMissingImports]


@functools.cache
def optimize_hidream_image_pipeline_memory_footprint(pipe) -> None:
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is required for HiDream Image pipeline optimization")
    
    pipe.to("cuda")


def print_hidream_image_pipeline_memory_footprint(pipe) -> None:
    print_pipeline_memory_footprint(
        pipe,
        [
            "transformer",
            "text_encoder",
            "tokenizer",
            "vae",
            "scheduler"
        ],
    )