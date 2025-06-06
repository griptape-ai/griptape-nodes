import logging
from functools import cache

import diffusers  # type: ignore[reportMissingImports]
import torch  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.utils.torch_utils import (  # type: ignore[reportMissingImports]
    get_best_device,
    print_pipeline_memory_footprint,
)

logger = logging.getLogger("diffusers_nodes_library")


def print_shap_e_pipeline_memory_footprint(pipe: diffusers.ShapEPipeline) -> None:
    """Print pipeline memory footprint."""
    print_pipeline_memory_footprint(
        pipe,
        [
            "prior",
            "image_encoder",
            "image_processor",
        ],
    )


@cache
def optimize_shap_e_pipeline_memory_footprint(pipe: diffusers.ShapEPipeline) -> None:
    """Optimize pipeline memory footprint."""
    device = get_best_device()

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is required for memory optimization")

    if device == torch.device("cuda"):
        logger.info("Enabling sequential cpu offload")
        pipe.enable_sequential_cpu_offload()

    logger.info("Enabling attention slicing")
    pipe.enable_attention_slicing()

    logger.info("Final memory footprint:")
    print_shap_e_pipeline_memory_footprint(pipe)

    if device == torch.device("mps"):
        logger.info("Transferring model to MPS/GPU - may take minutes")
        pipe.to(device)

    if device == torch.device("cuda"):
        pass