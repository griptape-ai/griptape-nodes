import functools

import torch  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.utils.torch_utils import print_pipeline_memory_footprint  # type: ignore[reportMissingImports]


@functools.cache
def optimize_deprecated_pipeline_memory_footprint(pipe) -> None:
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is required for deprecated pipeline optimization")
    
    pipe.to("cuda")


def print_deprecated_pipeline_memory_footprint(pipe) -> None:
    print_pipeline_memory_footprint(
        pipe,
        [
            "transformer",
            "text_encoder", 
            "text_encoder_2",
            "tokenizer",
            "tokenizer_2",
            "unet",
            "vae",
            "scheduler",
            "safety_checker",
            "feature_extractor"
        ],
    )