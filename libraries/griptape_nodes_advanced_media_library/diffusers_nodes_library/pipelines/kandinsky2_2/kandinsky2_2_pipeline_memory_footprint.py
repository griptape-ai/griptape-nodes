import logging
from functools import cache

import diffusers  # type: ignore[reportMissingImports]
import torch  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.utils.torch_utils import (
    get_best_device,  # type: ignore[reportMissingImports]
    print_pipeline_memory_footprint,  # type: ignore[reportMissingImports]
)

logger = logging.getLogger("diffusers_nodes_library")


def print_kandinsky2_2_pipeline_memory_footprint(
    pipe: diffusers.KandinskyV22Pipeline
    | diffusers.KandinskyV22Img2ImgPipeline
    | diffusers.KandinskyV22InpaintPipeline,  # type: ignore[reportMissingImports]
) -> None:
    """Print memory footprint for the main sub-modules of Kandinsky 2.2 pipelines."""
    print_pipeline_memory_footprint(
        pipe,
        [
            "text_encoder",
            "unet",
            "movq",
        ],
    )


@cache
def optimize_kandinsky2_2_pipeline_memory_footprint(
    pipe: diffusers.KandinskyV22Pipeline
    | diffusers.KandinskyV22Img2ImgPipeline
    | diffusers.KandinskyV22InpaintPipeline,  # type: ignore[reportMissingImports]
) -> None:
    """Apply a set of heuristics to minimise VRAM / RAM footprint at inference time.

    The logic follows the same rationale as the optimization helper for the Flux
    pipelines but adapted to the component layout of Kandinsky 2.2.
    """
    device = get_best_device()

    if not torch.cuda.is_available():
        msg = "CUDA is required for Kandinsky 2.2 pipeline optimization"
        raise RuntimeError(msg)

    if device == torch.device("cuda"):
        # Avoid blindly moving the whole pipeline to CUDA. Instead rely on
        # Diffusers' built-in sequential offload helper which swaps modules
        # between CPU ↔ GPU as needed.
        logger.info("Enabling sequential CPU offload")
        pipe.enable_sequential_cpu_offload()
    else:
        # For MPS / CPU back-ends we *do* need to call .to(device).
        logger.info("Transferring model to %s — may take a while the first time", device)
        pipe.to(device)

    # Attention and decoder slicing help a lot on constrained hardware.
    logger.info("Enabling attention slicing")
    pipe.enable_attention_slicing()

    if hasattr(pipe, "movq") and hasattr(pipe.movq, "enable_slicing"):
        logger.info("Enabling MoVQ slicing")
        pipe.movq.enable_slicing()  # type: ignore[attr-defined]

    logger.info("Final memory footprint:")
    print_kandinsky2_2_pipeline_memory_footprint(pipe)
