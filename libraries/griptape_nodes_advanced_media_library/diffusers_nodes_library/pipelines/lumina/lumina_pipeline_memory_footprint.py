import logging
from functools import cache

import diffusers  # type: ignore[reportMissingImports]
import torch  # type: ignore[reportMissingImports]
import torch.nn.functional  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.utils.torch_utils import (  # type: ignore[reportMissingImports]
    get_best_device,
    print_pipeline_memory_footprint,
)

logger = logging.getLogger("diffusers_nodes_library")


def print_lumina_pipeline_memory_footprint(pipe: diffusers.LuminaText2ImgPipeline) -> None:
    """Print pipeline memory footprint."""
    print_pipeline_memory_footprint(
        pipe,
        [
            "vae",
            "transformer",
            "text_encoder",
        ],
    )


@cache
def optimize_lumina_pipeline_memory_footprint(pipe: diffusers.LuminaText2ImgPipeline) -> None:
    """Optimize pipeline memory footprint."""
    device = get_best_device()

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is required for Lumina pipeline optimization")

    if device == torch.device("cuda"):
        # Sequential cpu offload only makes sense for gpus (VRAM <-> RAM).
        logger.info("Enabling sequential cpu offload")
        pipe.enable_sequential_cpu_offload()
    
    # TODO: https://github.com/griptape-ai/griptape-nodes/issues/846
    logger.info("Enabling attention slicing")
    pipe.enable_attention_slicing()
    
    # TODO: https://github.com/griptape-ai/griptape-nodes/issues/846
    if hasattr(pipe, "enable_vae_slicing"):
        logger.info("Enabling vae slicing")
        pipe.enable_vae_slicing()
    elif hasattr(pipe, "vae"):
        logger.info("Enabling vae slicing")
        pipe.vae.enable_slicing()

    logger.info("Final memory footprint:")
    print_lumina_pipeline_memory_footprint(pipe)