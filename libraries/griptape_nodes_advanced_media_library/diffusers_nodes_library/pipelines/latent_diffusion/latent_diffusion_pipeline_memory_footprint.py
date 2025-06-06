import logging
from functools import cache

import diffusers  # type: ignore[reportMissingImports]
import torch  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.utils.torch_utils import (
    get_best_device,  # type: ignore[reportMissingImports]
    print_pipeline_memory_footprint,  # type: ignore[reportMissingImports]
)

logger = logging.getLogger("diffusers_nodes_library")


def print_latent_diffusion_pipeline_memory_footprint(
    pipe: diffusers.LDMTextToImagePipeline,  # type: ignore[reportMissingImports]
) -> None:
    """Print memory footprint for the main sub-modules of Latent Diffusion pipelines."""
    print_pipeline_memory_footprint(
        pipe,
        [
            "bert",
            "unet",
            "vqvae",
        ],
    )


@cache  # noqa: B019
def optimize_latent_diffusion_pipeline_memory_footprint(
    pipe: diffusers.LDMTextToImagePipeline,  # type: ignore[reportMissingImports]
) -> None:
    """Apply a set of heuristics to minimise VRAM / RAM footprint at inference time.

    The logic follows the same rationale as the optimisation helper for other
    diffusers pipelines but adapted to the component layout of Latent Diffusion.
    """
    device = get_best_device()

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is required for LatentDiffusion pipeline optimization")

    logger.info("Enabling sequential CPU offload")
    pipe.enable_sequential_cpu_offload()

    logger.info("Enabling attention slicing")
    pipe.enable_attention_slicing()

    if hasattr(pipe, "vqvae") and hasattr(pipe.vqvae, "enable_slicing"):
        logger.info("Enabling VQ-VAE slicing")
        pipe.vqvae.enable_slicing()  # type: ignore[attr-defined]

    logger.info("Final memory footprint:")
    print_latent_diffusion_pipeline_memory_footprint(pipe)