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


def print_audio_ldm_pipeline_memory_footprint(pipe: diffusers.AudioLDMPipeline) -> None:
    """Print the memory footprint of the AudioLDM pipeline."""
    print_pipeline_memory_footprint(
        pipe,
        [
            "vae",
            "text_encoder",
            "unet",
            "vocoder",
        ],
    )


@cache
def optimize_audio_ldm_pipeline_memory_footprint(pipe: diffusers.AudioLDMPipeline) -> None:
    """Optimize pipeline memory footprint."""
    device = get_best_device()

    if device == torch.device("cuda"):
        # We specifically do not call pipe.to(device) for gpus
        # because it would move ALL the models in the pipe to the
        # gpus, potentially causing us to exhaust available VRAM,
        # and essentially undo all of the following VRAM pressure
        # reducing optimizations in vain.
        #
        # TL;DR - DONT CALL `pipe.to(device)` FOR GPUS!
        # (unless you checked pipe is small enough!)

        if hasattr(pipe, "transformer"):
            # This fp8 layerwise caching is important for lower VRAM
            # gpus (say 25GB or lower). Not important if not on a gpu.
            # We only do this for the transformer, because its the biggest.
            # TODO: https://github.com/griptape-ai/griptape-nodes/issues/846
            logger.info("Enabling fp8 layerwise caching for transformer")
            pipe.transformer.enable_layerwise_casting(
                storage_dtype=torch.float8_e4m3fn,
                compute_dtype=torch.bfloat16,
            )
        # Sequential cpu offload only makes sense for gpus (VRAM <-> RAM).
        # TODO: https://github.com/griptape-ai/griptape-nodes/issues/846
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
    print_audio_ldm_pipeline_memory_footprint(pipe)

    if device == torch.device("mps"):
        # We are not calling pipe.to(device) for mps for this pipeline
        # because it seems that it is not MPS compatible. Attempting to
        # call pipe.to(device) will result in the following error:
        #
        # MPS error: -- Output channels > 65536 not supported at the MPS device
        pass

    if device == torch.device("cuda"):
        # We specifically do not call pipe.to(device) for gpus
        # because it would move ALL the models in the pipe to the
        # gpus, potentially causing us to exhaust available VRAM,
        # and essentially undo all of the following VRAM pressure
        # reducing optimizations in vain.
        #
        # TL;DR - DONT CALL `pipe.to(device)` FOR GPUS!
        # (unless you checked pipe is small enough!)
        pass
