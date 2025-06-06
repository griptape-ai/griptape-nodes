import functools
import logging

import diffusers  # type: ignore[reportMissingImports]
import torch  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.utils.torch_utils import print_pipeline_memory_footprint  # type: ignore[reportMissingImports]

logger = logging.getLogger("diffusers_nodes_library")


@functools.cache
def optimize_consisid_pipeline_memory_footprint(pipe: diffusers.ConsisIDPipeline) -> None:
    """Optimize ConsisID pipeline memory footprint for CUDA."""
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is not available. Memory optimization requires CUDA.")
    
    logger.info("Optimizing ConsisID pipeline memory footprint")
    device = torch.device("cuda")
    pipe = pipe.to(device)
    
    # Enable memory optimizations
    pipe.enable_model_cpu_offload()
    pipe.vae.enable_slicing()
    pipe.vae.enable_tiling()


def print_consisid_pipeline_memory_footprint(pipe: diffusers.ConsisIDPipeline) -> None:
    """Print memory footprint of ConsisID pipeline components."""
    sub_modules = ["transformer", "vae", "text_encoder", "face_helper_1", "face_helper_2"]
    print_pipeline_memory_footprint(pipe, sub_modules)