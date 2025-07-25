import logging

import diffusers  # type: ignore[reportMissingImports]
import torch  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.utils.torch_utils import (
    get_best_device,
    get_total_memory_footprint,  # type: ignore[reportMissingImports]
    print_pipeline_memory_footprint,
    to_human_readable_size,  # type: ignore[reportMissingImports]
)

logger = logging.getLogger("diffusers_nodes_library")


COSMOS_2_TEXT_TO_IMAGE_PIPELINE_COMPONENT_NAMES = [
    "text_encoder",
    "transformer",
    "vae",
]


def print_cosmos_2_text_to_image_pipeline_memory_footprint(
    pipe: diffusers.Cosmos2TextToImagePipeline,  # type: ignore[reportMissingImports]
) -> None:
    """Print memory footprint for the main sub-modules of Cosmos2 text-to-image pipelines."""
    print_pipeline_memory_footprint(pipe, COSMOS_2_TEXT_TO_IMAGE_PIPELINE_COMPONENT_NAMES)


def optimize_cosmos_2_text_to_image_pipeline_memory_footprint(
    pipe: diffusers.Cosmos2TextToImagePipeline,  # type: ignore[reportMissingImports]
) -> None:
    """Apply a minimal set of optimizations and move the pipeline to the best device."""
    device = get_best_device()

    # Move to device early so that subsequent calls use the correct default device.
    logger.info("Transferring pipeline to %s", device)

    model_memory = get_total_memory_footprint(pipe, COSMOS_2_TEXT_TO_IMAGE_PIPELINE_COMPONENT_NAMES)

    if device.type == "cuda":
        total_memory = torch.cuda.get_device_properties(device).total_memory
        free_memory = total_memory - torch.cuda.memory_allocated(device)
        logger.info("Total memory on %s: %s", device, to_human_readable_size(total_memory))
        logger.info("Free memory on %s: %s", device, to_human_readable_size(free_memory))
        logger.info("Require memory for Cosmos2 Pipeline: %s", to_human_readable_size(model_memory))
        if model_memory <= free_memory:
            logger.info("Sufficient memory on %s for Pipeline.", device)
            logger.info("Moving pipeline to %s", device)
            pipe.to(device)
        else:
            logger.warning("Insufficient memory on %s for Pipeline.", device)
    elif device.type == "mps":
        recommended_max_memory = torch.mps.recommended_max_memory()
        free_memory = recommended_max_memory - torch.mps.current_allocated_memory()
        logger.info("Recommended max memory on %s: %s", device, to_human_readable_size(recommended_max_memory))
        logger.info("Free memory on %s: %s", device, to_human_readable_size(free_memory))
        logger.info("Require memory for Pipeline: %s", to_human_readable_size(model_memory))
        if model_memory <= free_memory:
            logger.info("Sufficient memory on %s for Pipeline.", device)
            logger.info("Moving pipeline to %s", device)
            pipe.to(device)
        else:
            logger.warning("Insufficient memory on %s for Pipeline.", device)

    logger.info("Final memory footprint:")
    print_cosmos_2_text_to_image_pipeline_memory_footprint(pipe)
