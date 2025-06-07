import logging
from functools import cache

import diffusers  # type: ignore[reportMissingImports]
import torch  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.utils.torch_utils import (
    get_best_device,  # type: ignore[reportMissingImports]
    print_pipeline_memory_footprint,  # type: ignore[reportMissingImports]
)

logger = logging.getLogger("diffusers_nodes_library")


def print_kolors_pipeline_memory_footprint(
    pipe: diffusers.KolorsPipeline,  # type: ignore[reportMissingImports]
) -> None:
    """Print memory footprint for the main sub-modules of Kolors pipelines."""
    print_pipeline_memory_footprint(
        pipe,
        [
            "text_encoder",
            "unet",
            "vae",
        ],
    )


@cache
def optimize_kolors_pipeline_memory_footprint(
    pipe: diffusers.KolorsPipeline,  # type: ignore[reportMissingImports]
) -> None:
    """Apply a set of heuristics to minimise VRAM / RAM footprint at inference time.

    The logic follows the same rationale as the optimisation helper for other
    diffusers pipelines but adapted to the component layout of Kolors.
    """
    get_best_device()

    if not torch.cuda.is_available():
        msg = "CUDA is required for Kolors pipeline optimization"
        raise RuntimeError(msg)

    logger.info("Enabling sequential CPU offload")
    pipe.enable_sequential_cpu_offload()

    logger.info("Enabling attention slicing")
    pipe.enable_attention_slicing()

    if hasattr(pipe, "vae") and hasattr(pipe.vae, "enable_slicing"):
        logger.info("Enabling VAE slicing")
        pipe.vae.enable_slicing()  # type: ignore[attr-defined]

    logger.info("Final memory footprint:")
    print_kolors_pipeline_memory_footprint(pipe)
