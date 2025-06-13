import functools
import logging

import diffusers  # type: ignore[reportMissingImports]
import torch  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.utils.torch_utils import (
    print_pipeline_memory_footprint,  # type: ignore[reportMissingImports]
)

logger = logging.getLogger("diffusers_nodes_library")


@functools.cache
def optimize_cogview3_pipeline_memory_footprint(pipe: diffusers.CogView3PlusPipeline) -> None:
    """Optimize CogView3Plus pipeline memory footprint for CUDA."""
    if not torch.cuda.is_available():
        msg = "CUDA is not available. Memory optimization requires CUDA."
        raise RuntimeError(msg)

    logger.info("Optimizing CogView3Plus pipeline memory footprint")
    device = torch.device("cuda")
    pipe = pipe.to(device)

    # Enable memory optimizations
    pipe.enable_model_cpu_offload()
    pipe.vae.enable_slicing()
    pipe.vae.enable_tiling()


def print_cogview3_pipeline_memory_footprint(pipe: diffusers.CogView3PlusPipeline) -> None:
    """Print memory footprint of CogView3Plus pipeline components."""
    sub_modules = ["transformer", "vae", "text_encoder", "tokenizer"]
    print_pipeline_memory_footprint(pipe, sub_modules)
